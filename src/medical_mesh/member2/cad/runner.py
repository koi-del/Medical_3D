from pathlib import Path
from time import perf_counter
from uuid import uuid4
import json
import os
import shutil
import subprocess
import numpy as np

from medical_mesh.member2.core.model import MeshAsset, load_preview, save_asset, write_json, file_hash
from medical_mesh.member2.evaluation import evaluate_mesh, EvaluationConfig

FORMATS = {"stl": "stl", "step": "step", "stp": "step", "igs": "igs", "iges": "igs"}
LOCAL_CONFIG = Path(__file__).resolve().parents[4] / "configs/freecad.local.json"
DEFAULTS = {
    "timeout_seconds": 120, "max_stl_faces": 3000, "representation": "surface",
    "sewing_tolerance_mm": .01, "linear_deflection_mm": .03, "angular_deflection_rad": .2,
    "readback_linear_deflection_mm": .01, "readback_angular_deflection_rad": .1,
    "source_linear_deflection_mm": .005, "source_angular_deflection_rad": .075,
    "coarse_linear_deflection_mm": .02, "coarse_angular_deflection_rad": .15,
    "samples": 5000, "seed": 20261018, "coordinate_tolerance_mm": .1,
    "d95_mm": .1, "sampled_max_mm": .3, "convergence_tolerance_mm": .02,
    "max_readback_faces": 500000,
}


def effective_config(config=None):
    local = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8")) if LOCAL_CONFIG.exists() else {}
    return {**DEFAULTS, **local, **(config or {})}


def probe_freecad(config=None):
    config = effective_config(config)
    executable = config.get("executable") or os.environ.get("FREECAD_EXECUTABLE")
    if not executable:
        executable = shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    if not executable and os.name=='nt':
        for base in (os.environ.get('ProgramFiles','C:/Program Files'),os.environ.get('LOCALAPPDATA','')):
            matches=sorted(Path(base).glob('FreeCAD*/bin/FreeCADCmd.exe'),reverse=True) if base else []
            if matches:executable=str(matches[0]);break
    if not executable:
        candidates = [Path(base) / relative for base in ("/Applications/FreeCAD.app", str(Path.home()/"Applications/FreeCAD.app"))
                      for relative in ("Contents/Resources/bin/FreeCADCmd", "Contents/Resources/bin/freecadcmd", "Contents/MacOS/FreeCADCmd")]
        executable = next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)
    if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        return {"status": "unavailable", "executable": executable,
                "reason": "FreeCAD runner not installed/configured"}
    return {"status": "configured", "executable": str(Path(executable).absolute()),
            "arguments": config.get("arguments", ["{script}"]), "config_path": str(LOCAL_CONFIG) if LOCAL_CONFIG.exists() else None}


def validate_config(config):
    positive = ["timeout_seconds", "sewing_tolerance_mm", "linear_deflection_mm", "angular_deflection_rad",
                "readback_linear_deflection_mm", "readback_angular_deflection_rad", "source_linear_deflection_mm",
                "source_angular_deflection_rad", "coarse_linear_deflection_mm", "coarse_angular_deflection_rad"]
    nonnegative = ["coordinate_tolerance_mm", "d95_mm", "sampled_max_mm", "convergence_tolerance_mm"]
    for name in positive + nonnegative:
        value = config[name]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or value < 0 or (name in positive and value == 0):
            raise ValueError(f"invalid CAD configuration: {name}")
    for name in ("samples", "max_stl_faces", "max_readback_faces"):
        if type(config[name]) is not int or config[name] < 1:
            raise ValueError(f"invalid CAD configuration: {name}")
    for name in ("angular_deflection_rad", "readback_angular_deflection_rad", "source_angular_deflection_rad", "coarse_angular_deflection_rad"):
        if config[name] >= np.pi:
            raise ValueError("angular deflection must be below pi")
    if (config["readback_linear_deflection_mm"] > config["coarse_linear_deflection_mm"]
            or config["source_linear_deflection_mm"] > config["coarse_linear_deflection_mm"]):
        raise ValueError("fine/reference tessellation must not be coarser than coarse validation")


def run_worker(config, request, directory, label):
    config = effective_config(config)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    info = probe_freecad(config)
    if info["status"] == "unavailable":
        raise RuntimeError(info["reason"])
    request_path, result_path = directory/f"{label}_request.json", directory/f"{label}_result.json"
    request_id = uuid4().hex
    write_json(request_path, {**request, "request_id": request_id, "result_path": str(result_path)})
    worker_directory = Path(__file__).resolve().parent
    # FreeCAD's Windows argv decoder corrupts non-ASCII absolute script paths.
    # The environment job path remains Unicode; execute the ASCII basename locally.
    script = "freecad_worker.py" if os.name == 'nt' else str(worker_directory / "freecad_worker.py")
    args = [x.replace("{script}", script) for x in info["arguments"]]
    env = os.environ.copy()
    env["MEDICAL_MESH_CAD_JOB"] = str(request_path)
    for name in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    timeout = float(config["timeout_seconds"])
    if not np.isfinite(timeout) or timeout <= 0:
        raise ValueError("positive timeout required")
    with (directory/f"{label}_stdout.log").open("wb") as out, (directory/f"{label}_stderr.log").open("wb") as err:
        with subprocess.Popen([info['executable'],*args],env=env,cwd=worker_directory,stdout=out,stderr=err,stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0) as process:
            try:process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name=='nt':
                    from ..processes import stop_windows_tree
                    stop_windows_tree(process.pid)
                else:process.kill()
                process.wait(timeout=10)
                raise
    if process.returncode or not result_path.exists():
        raise RuntimeError(f"FreeCAD worker failed ({process.returncode}); see {label}_stderr.log")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("request_id") != request_id or result.get("mode") != request["mode"]:
        raise RuntimeError("FreeCAD returned stale or mismatched job result")
    if result.get("status") != "completed":
        raise RuntimeError(result.get("error", "FreeCAD result incomplete"))
    return result


def read_mesh(result):
    arrays = json.loads(Path(result["mesh_json"]).read_text(encoding="utf-8"))
    return MeshAsset(np.asarray(arrays["vertices"]), np.asarray(arrays["faces"], dtype=np.int64),
                     unit_status="confirmed", unit_name="mm", unit_to_mm=1.)


def inspect_file(config, source, fmt, directory, label, linear, angular):
    return run_worker(config, {"mode": "inspect", "input_path": str(source), "source_format": fmt,
                              "linear_deflection_mm": linear, "angular_deflection_rad": angular,
                              "max_readback_faces": config["max_readback_faces"]}, directory, label)


def conversion_checks(metrics, coarse_metrics, bbox_delta, config):
    convergence = max(abs(metrics[k]-coarse_metrics[k]) for k in ("asd", "d95", "sampled_max"))
    checks = {"coordinate_bbox": bbox_delta <= config["coordinate_tolerance_mm"],
              "d95": metrics["d95"] <= config["d95_mm"],
              "sampled_max": metrics["sampled_max"] <= config["sampled_max_mm"],
              "tessellation_stability": convergence <= config["convergence_tolerance_mm"]}
    return checks, float(convergence)


def convert_file(input_path, target_format, config, directory, unit=None, progress=lambda *_: None):
    config = effective_config(config)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/"conversion_result.json").exists():
        raise FileExistsError("conversion run already exists; use a fresh directory")
    started = perf_counter()
    source = Path(input_path).resolve()
    source_format = FORMATS.get(source.suffix.lower().lstrip("."))
    target = FORMATS.get(target_format.lower())
    result = {"operation": "convert", "status": "failed", "quality_status": "unverified",
              "validation_scope": "conversion_roundtrip_sampled_geometry_not_full_mesh_or_clinical_validation",
              "decision": "not_applicable", "source_format": source_format, "target_format": target,
              "export_status": "not_run", "readback_status": "not_run", "geometry_status": "not_run",
              "config": config, "input_path": str(source)}
    try:
        progress("preparing", "检查转换输入、单位和参数")
        validate_config(config)
        if not source_format or not target or source_format == target:
            raise ValueError("choose one of the six distinct STL/STEP/IGS directions")
        if not source.is_file():
            raise ValueError("input file does not exist")
        result["input_sha256"] = file_hash(source)
        if probe_freecad(config)["status"] == "unavailable":
            result.update(status="unavailable", reason_codes=["FREECAD_UNAVAILABLE"])
            return result
        cad_input, reference = source, None
        if source_format == "stl":
            asset = load_preview(source, unit)
            if asset.unit_status != "confirmed":
                raise ValueError("STL unit must be explicitly confirmed before CAD conversion")
            if len(asset.faces) > config["max_stl_faces"]:
                raise ValueError("CAD face budget exceeded; explicitly generate an evaluated simplified copy")
            reference = MeshAsset(asset.vertices*asset.unit_to_mm, asset.faces,
                                  unit_status="confirmed", unit_name="mm", unit_to_mm=1.)
            import trimesh
            cad_input = directory/"input_mm.stl"
            trimesh.Trimesh(reference.vertices, reference.faces, process=False).export(str(cad_input))
            reference_bbox = [reference.vertices.min(axis=0).tolist(), reference.vertices.max(axis=0).tolist()]
            result["unit_transform"] = {"source_unit": asset.unit_name, "factor_to_mm": asset.unit_to_mm,
                                        "applied_once": True}
        output = directory/("converted."+target)
        progress("exporting", "FreeCAD写出目标文件")
        exported = run_worker(config, {"mode": "convert", "input_path": str(cad_input), "output_path": str(output),
                              "source_format": source_format, "target_format": target,
                              "representation": config["representation"], "sewing_tolerance_mm": config["sewing_tolerance_mm"],
                              "linear_deflection_mm": config["linear_deflection_mm"],
                              "angular_deflection_rad": config["angular_deflection_rad"]}, directory, "export")
        if not output.exists() or not output.stat().st_size:
            raise RuntimeError("export did not produce a nonempty file")
        result.update(export_status="written", output_path=str(output), output_sha256=file_hash(output), export=exported)
        progress("readback_fine", "新进程回读目标文件（细档）")
        fine = inspect_file(config, output, target, directory, "readback_fine", config["readback_linear_deflection_mm"], config["readback_angular_deflection_rad"])
        result.update(readback_status="loaded", readback=fine)
        progress("readback_coarse", "独立回读第二档离散，检查稳定性")
        coarse = inspect_file(config, output, target, directory, "readback_coarse", config["coarse_linear_deflection_mm"], config["coarse_angular_deflection_rad"])
        candidate, coarse_candidate = read_mesh(fine), read_mesh(coarse)
        if reference is None:
            progress("source_reference", "读取原CAD参考，核对位置和尺寸")
            source_fine = inspect_file(config, source, source_format, directory, "source_fine", config["source_linear_deflection_mm"], config["source_angular_deflection_rad"])
            source_coarse = inspect_file(config, source, source_format, directory, "source_coarse", config["coarse_linear_deflection_mm"], config["coarse_angular_deflection_rad"])
            reference, coarse_reference = read_mesh(source_fine), read_mesh(source_coarse)
            reference_bbox = source_fine["bbox_mm"]
            result.update(reference_kind="CAD_fine_tessellation_proxy_not_exact_surface", source_readback=source_fine)
        else:
            coarse_reference = reference
            result["reference_kind"] = "original_STL_scaled_to_mm"
        evaluation = EvaluationConfig(config["samples"], config["seed"])
        progress("evaluating", "计算双向表面偏差和离散稳定性")
        metrics, details = evaluate_mesh(reference, candidate, evaluation)
        coarse_metrics, _ = evaluate_mesh(coarse_reference, coarse_candidate, evaluation)
        np.savez_compressed(directory/"conversion_samples.npz", **details)
        preview_reference = save_asset(reference, directory/"reference_readback.npz")
        preview_candidate = save_asset(candidate, directory/"candidate_readback.npz")
        result["preview_assets"] = {"reference": str(preview_reference), "candidate": str(preview_candidate),
                                    "distances": str(directory/"conversion_samples.npz")}
        bbox_delta = float(np.max(np.abs(np.asarray(reference_bbox)-np.asarray(fine["bbox_mm"]))))
        checks, convergence = conversion_checks(metrics, coarse_metrics, bbox_delta, config)
        checks["independent_readback_process"] = len({exported["pid"], fine["pid"], coarse["pid"]}) == 3
        checks["valid_cad_readback"] = fine.get("valid") is not False
        passed = all(checks.values())
        result.update(status="completed", geometry_status="passed" if passed else "failed",
                      quality_status="passed" if passed else "failed", decision="accepted" if passed else "rejected",
                      metrics=metrics, coarse_metrics=coarse_metrics, readback_coarse=coarse,
                      checks=checks, bbox_max_delta_mm=bbox_delta, reference_bbox_mm=reference_bbox,
                      convergence_delta_mm=convergence, actual_representation=fine["actual_representation"],
                      reason_codes=[name.upper()+"_FAILED" for name, value in checks.items() if not value],
                      limitations=["finite sampled surface distances, not exact Hausdorff",
                                   "CAD source uses fine tessellation proxy; two-level stability is empirical",
                                   "full mesh/self-intersection/ROI qualification remains with integrated pipeline",
                                   "STL-derived CAD uses surface policy; no parametric history recovery or solid claim",
                                   "same OpenCASCADE kernel readback does not prove NX or all-vendor compatibility"])
        if config.get("write_error_figure", True):
            from medical_mesh.member2.reporting.report import error_figure
            error_figure(details, directory/"error.png")
    except subprocess.TimeoutExpired:
        result.update(status="timeout", errors=["FreeCAD worker timeout"], reason_codes=["CAD_TIMEOUT"])
    except Exception as error:
        result.update(status="failed", errors=[str(error)], reason_codes=["CAD_ERROR"])
    finally:
        result["elapsed_seconds"] = perf_counter()-started
        write_json(directory/"conversion_result.json", result)
    return result
