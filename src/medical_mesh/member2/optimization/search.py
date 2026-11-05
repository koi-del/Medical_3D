from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
import importlib
import numpy as np

from medical_mesh.member2.core.model import save_asset
from medical_mesh.member2.evaluation import evaluate_mesh, EvaluationConfig
from .filters import process_mesh
from ..evaluation.verified_volume import enrich_volume


@dataclass(frozen=True)
class Limits:
    d95_normalized: float = .001
    sampled_max_normalized: float = .003
    area_change: float = .01

    def __post_init__(self):
        if any(not np.isfinite(x) or x < 0 for x in asdict(self).values()):
            raise ValueError("limits must be finite and nonnegative")


REQUIRED_CHECKS = ("reference_eligible", "duplicate_faces", "degenerate_faces",
                   "nonmanifold_edges", "nonmanifold_vertices", "orientation",
                   "self_intersection", "component_correspondence", "boundary_correspondence",
                   "protected_rois")


def check_diagnosis(provider, reference, candidate):
    if provider is None:
        return {"status": "unverified", "reason": "MEMBER1_DIAGNOSTIC_SERVICE_MISSING", "checks": {}}
    try:
        result = provider(reference, candidate)
        if result.get("reference_version") != reference.version_id or result.get("input_version") != candidate.version_id:
            raise ValueError("diagnosis version mismatch")
        if result.get("geometry_sha256") != candidate.geometry_hash:
            raise ValueError("diagnosis geometry hash mismatch")
        if result.get("scope") != "production":
            return {"status": "unverified", "reason": "FIXTURE_OR_UNDECLARED_SCOPE", "details": result}
        checks = result.get("checks", {})
        # not_applicable is an explicit provider assertion for this reference, never a missing field.
        if any(checks.get(k) == "failed" for k in REQUIRED_CHECKS):
            return {"status": "failed", "reason": "STRUCTURAL_CHECK_FAILED", "details": result}
        core = set(REQUIRED_CHECKS) - {"boundary_correspondence", "protected_rois"}
        if (not all(checks.get(k) == "passed" for k in core)
                or not all(checks.get(k) in {"passed", "not_applicable"} for k in REQUIRED_CHECKS)):
            return {"status": "unverified", "reason": "REQUIRED_CHECK_UNAVAILABLE", "details": result}
        return {"status": "passed", "details": result}
    except Exception as error:
        return {"status": "unverified", "reason": "DIAGNOSTIC_ERROR", "error": str(error)}


def load_provider(spec):
    if not spec:
        return None
    module, name = spec.split(":", 1)
    return getattr(importlib.import_module(module), name)


def geometry_reasons(metrics, limits):
    reasons = []
    for field, code in (("d95_normalized", "D95_LIMIT_EXCEEDED"),
                        ("sampled_max_normalized", "SAMPLED_MAX_LIMIT_EXCEEDED"),
                        ("area_change", "AREA_LIMIT_EXCEEDED")):
        if not np.isfinite(metrics[field]) or metrics[field] > getattr(limits, field):
            reasons.append(code)
    if metrics["candidate_quality"]["zero_area_faces"]:
        reasons.append("ZERO_AREA_FACE")
    return reasons


def optimize_mesh(reference, configs, output_dir, config=None, final_config=None,
                  limits=None, diagnostic_service=None, progress=lambda *_: None):
    config, limits = config or EvaluationConfig(), limits or Limits()
    final_config = final_config or EvaluationConfig(max(50000, config.samples), config.seed + 10000)
    if final_config.samples < config.samples or final_config.seed == config.seed:
        raise ValueError("final evaluation needs at least screening density and an independent seed")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    attempts, candidates = [], {}
    for index, parameters in enumerate(configs):
        progress("generating_candidate", f"candidate {index+1}/{len(configs)}")
        item = {"candidate_id": f"candidate_{index:02d}", "parameters": parameters,
                "status": "running", "decision": "rejected", "reason_codes": []}
        begin = perf_counter()
        try:
            candidate = process_mesh(reference, parameters)
            item["processing_seconds"] = perf_counter() - begin
            candidates[item["candidate_id"]] = candidate
            path = save_asset(candidate, output_dir / (item["candidate_id"] + ".npz"))
            item.update(mesh_path=str(path.resolve()), actual_faces=len(candidate.faces),version_id=candidate.version_id,
                        geometry_sha256=candidate.geometry_hash)
            progress("diagnosing", item["candidate_id"])
            item["diagnosis"] = check_diagnosis(diagnostic_service, reference, candidate)
            progress("evaluating", item["candidate_id"])
            metrics, details = evaluate_mesh(reference, candidate, config)
            enrich_volume(metrics,reference,candidate,item['diagnosis'])
            item["metrics"] = metrics
            np.savez_compressed(output_dir / (item["candidate_id"] + "_screening.npz"), **details)
            item["reason_codes"] = geometry_reasons(metrics, limits)
            if item["diagnosis"]["status"] == "failed":
                item["reason_codes"].append("STRUCTURAL_CHECK_FAILED")
            item["screening_passed"] = not item["reason_codes"]
            item["status"] = "completed"
            if item["screening_passed"]:
                item["decision"] = "needs_review"
        except Exception as error:
            item.update(status="failed", screening_passed=False, error=str(error))
            item["reason_codes"].append("CANDIDATE_FAILED")
        item["elapsed_seconds"] = perf_counter() - begin
        attempts.append(item)
    ranked = sorted((x for x in attempts if x.get("screening_passed")),
                    key=lambda x: (x["actual_faces"], x["metrics"]["d95"], x["processing_seconds"]))
    selected, preview = None, None
    for item in ranked:
        progress("final_check", item["candidate_id"])
        try:
            metrics, details = evaluate_mesh(reference, candidates[item["candidate_id"]], final_config)
            enrich_volume(metrics,reference,candidates[item['candidate_id']],item['diagnosis'])
            item["final_metrics"] = metrics
            np.savez_compressed(output_dir / (item["candidate_id"] + "_final.npz"), **details)
            reasons = geometry_reasons(metrics, limits)
            item["final_passed"] = not reasons
            item["reason_codes"].extend(reasons)
            if reasons:
                item["decision"] = "rejected"
                continue
            if preview is None:
                preview = item
            if item["diagnosis"]["status"] == "passed":
                item["decision"] = "accepted"
                selected = item
                break
            item["reason_codes"].append(item["diagnosis"].get("reason", "UNVERIFIED"))
        except Exception as error:
            item.update(final_passed=False, final_error=str(error), decision="rejected")
            item["reason_codes"].append("FINAL_CHECK_FAILED")
    if selected:
        decision, reason, quality = "accepted", [], "passed"
    elif preview:
        decision, reason, quality = "needs_review", ["REQUIRED_CHECK_UNAVAILABLE"], "unverified"
    else:
        decision, reason, quality = "rejected", ["NO_CANDIDATE_ACCEPTED"], "failed"
    return {"status": "completed", "decision": decision, "quality_status": quality,
            "input_version": reference.version_id,
            "output_version": candidates[selected["candidate_id"]].version_id if selected else None,
            "selected_candidate": selected["candidate_id"] if selected else None,
            "preview_candidate": preview["candidate_id"] if preview else None,
            "current_version_unchanged": True, "requires_user_commit": True,
            "reason_codes": reason, "limits": asdict(limits), "attempts": attempts,
            "elapsed_seconds": perf_counter()-started}


def verify_selected(reference,verification,candidate_id,output_dir,diagnostic_service=None,progress=lambda *_:None):
    """Evaluate the exact selected mesh, including candidates not initially finalized."""
    import copy
    from ..core.model import load_asset
    result=copy.deepcopy(verification);directory=Path(output_dir);directory.mkdir(parents=True,exist_ok=True)
    if result.get('input_version')!=reference.version_id:raise ValueError('Stale optimization reference')
    items=[x for x in result.get('attempts',[]) if x['candidate_id']==candidate_id]
    if len(items)!=1 or not items[0].get('screening_passed'):raise ValueError('Candidate did not pass screening')
    item=items[0];candidate=load_asset(item['mesh_path'])
    if (candidate.parent_version!=reference.version_id or candidate.asset_id!=reference.asset_id or
        candidate.version_id!=item.get('version_id') or candidate.geometry_hash!=item.get('geometry_sha256')):
        raise ValueError('Selected candidate identity mismatch')
    if item['metrics'].get('reference_hash')!=reference.geometry_hash:raise ValueError('Reference geometry mismatch')
    progress('final_check','独立复核所选方案，不重新生成或替换候选')
    diagnosis=check_diagnosis(diagnostic_service,reference,candidate)
    config=EvaluationConfig(max(50000,item['metrics']['samples_each_direction']),item['metrics']['seed_ab']+10000)
    metrics,details=evaluate_mesh(reference,candidate,config);enrich_volume(metrics,reference,candidate,diagnosis)
    path=save_asset(candidate,directory/(candidate_id+'.npz'))
    sample_path=directory/(candidate_id+'_final.npz');np.savez_compressed(sample_path,**details)
    reasons=geometry_reasons(metrics,Limits(**result.get('limits',{})))
    item.update(mesh_path=str(path.resolve()),final_metrics=metrics,diagnosis=diagnosis,
        final_samples_path=str(sample_path.resolve()),final_passed=not reasons,
        reason_codes=reasons+([] if diagnosis['status']=='passed' else [diagnosis.get('reason','UNVERIFIED')]))
    passed=not reasons and diagnosis['status']=='passed'
    item['decision']='accepted' if passed else ('needs_review' if not reasons and diagnosis['status']=='unverified' else 'rejected')
    result.update(status='completed',selected_candidate=candidate_id if passed else None,
        preview_candidate=candidate_id if not reasons else None,output_version=candidate.version_id if passed else None,
        decision=item['decision'],quality_status='passed' if passed else 'unverified' if not reasons else 'failed',
        verified_candidate=candidate_id,current_version_unchanged=True,requires_user_commit=True)
    return result,details
