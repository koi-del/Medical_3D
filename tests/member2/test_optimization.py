import numpy as np
import pytest
import trimesh

from medical_mesh.member2.core.model import MeshAsset
from medical_mesh.member2.evaluation import EvaluationConfig
from medical_mesh.member2.fixtures import open_tube
from medical_mesh.member2.optimization.filters import process_mesh, boundary_vertices
from medical_mesh.member2.optimization.search import optimize_mesh, Limits, check_diagnosis, REQUIRED_CHECKS


def sphere():
    mesh = trimesh.creation.icosphere(subdivisions=2)
    return MeshAsset(mesh.vertices, mesh.faces)


@pytest.mark.parametrize("method", ["laplacian", "taubin"])
def test_smoothing_fixes_open_boundary(method):
    asset = open_tube()
    ids, _ = boundary_vertices(asset)
    result = process_mesh(asset, {"operation": method, "iterations": 5})
    assert np.array_equal(result.vertices[ids], asset.vertices[ids])
    assert result.parent_version == asset.version_id
    assert not np.array_equal(result.vertices, asset.vertices)


@pytest.mark.parametrize("method", ["qem", "remesh"])
def test_real_pymeshlab_filters(method):
    asset = sphere()
    result = process_mesh(asset, {"operation": method, "keep_ratio": .5, "target_edge_length": .25, "iterations": 2})
    assert np.isfinite(result.vertices).all()
    assert len(result.faces) > 0
    if method == "qem":
        assert len(result.faces) < len(asset.faces)


def test_missing_diagnosis_cannot_auto_accept(tmp_path):
    asset = sphere()
    result = optimize_mesh(asset, [{"operation": "qem", "keep_ratio": .8}], tmp_path,
        EvaluationConfig(200, 2), EvaluationConfig(500, 8), Limits(1., 1., 1.))
    assert result["decision"] == "needs_review"
    assert result["quality_status"] == "unverified"
    assert result["output_version"] is None
    assert result["preview_candidate"]
    assert result["current_version_unchanged"]


def test_all_over_limit_retains_reference(tmp_path):
    asset = sphere()
    original = asset.geometry_hash
    result = optimize_mesh(asset, [{"operation": "qem", "keep_ratio": .1}], tmp_path,
        EvaluationConfig(300, 2), EvaluationConfig(500, 8), Limits(0., 0., 0.))
    assert result["decision"] == "rejected"
    assert result["selected_candidate"] is None
    assert result["output_version"] is None
    assert asset.geometry_hash == original


def test_candidates_use_same_reference(tmp_path):
    asset = sphere()
    result = optimize_mesh(asset, [{"operation": "qem", "keep_ratio": r} for r in (.8, .5)], tmp_path,
        EvaluationConfig(100, 2), EvaluationConfig(200, 8), Limits(1, 1, 1))
    assert all(x["metrics"]["reference_version"] == asset.version_id for x in result["attempts"])


def test_stale_or_fixture_diagnosis_never_verified():
    asset = sphere()
    def fixture(a, b):
        return {"scope": "fixture_only", "reference_version": a.version_id,
                "input_version": b.version_id, "geometry_sha256": b.geometry_hash,
                "checks": dict.fromkeys(REQUIRED_CHECKS, "passed")}
    assert check_diagnosis(fixture, asset, asset)["status"] == "unverified"
    def stale(a, b):
        value = fixture(a, b); value["scope"] = "production"; value["input_version"] = "old"
        return value
    assert check_diagnosis(stale, asset, asset)["status"] == "unverified"


def test_core_checks_cannot_be_not_applicable():
    asset = sphere()
    def invalid(a, b):
        return {"scope": "production", "reference_version": a.version_id,
                "input_version": b.version_id, "geometry_sha256": b.geometry_hash,
                "checks": dict.fromkeys(REQUIRED_CHECKS, "not_applicable")}
    assert check_diagnosis(invalid, asset, asset)["status"] == "unverified"


def test_final_recheck_can_reject_screened_candidate(tmp_path, monkeypatch):
    from medical_mesh.member2.optimization import search
    real = search.evaluate_mesh
    def evaluation(a, b, cfg):
        metrics, details = real(a, b, cfg)
        if cfg.seed == 8:
            metrics["d95_normalized"] = 999.
        return metrics, details
    monkeypatch.setattr(search, "evaluate_mesh", evaluation)
    result = optimize_mesh(sphere(), [{"operation": "qem", "keep_ratio": .8}], tmp_path,
        EvaluationConfig(100, 2), EvaluationConfig(200, 8), Limits(1, 1, 1))
    assert result["decision"] == "rejected"
    assert result["preview_candidate"] is None
    assert result["attempts"][0]["final_passed"] is False
