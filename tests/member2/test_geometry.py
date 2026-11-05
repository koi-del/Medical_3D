import json
import numpy as np
import pytest

from medical_mesh.member2.core.model import MeshAsset, save_asset, load_asset
from medical_mesh.member2.fixtures import plane, open_tube
from medical_mesh.member2.evaluation.metrics import (EvaluationConfig, evaluate_mesh, sample_surface,
                                              triangle_measures, surface_distances)


def test_self_surface_zero():
    asset = plane()
    result, _ = evaluate_mesh(asset, asset, EvaluationConfig(500, 7))
    assert result["sampled_max"] < 1e-12


def test_analytic_parallel_planes():
    result, _ = evaluate_mesh(plane(), plane(2.5), EvaluationConfig(800, 7))
    for key in ("asd", "d95", "sampled_max"):
        assert result[key] == pytest.approx(2.5, abs=1e-12)


def test_point_to_surface_not_nearest_vertex():
    distance, closest, _ = surface_distances(np.array([[.5, .5, 0.0]]), plane())
    assert distance[0] < 1e-12
    assert np.linalg.norm(plane().vertices-[.5, .5, 0.], axis=1).min() > .5


def test_retriangulation_same_surface():
    result, _ = evaluate_mesh(plane(), plane(subdivide=True), EvaluationConfig(800, 12))
    assert result["sampled_max"] < 1e-12


def test_far_coordinates_are_not_recentred_in_metadata():
    a, b = plane(), plane(2.5)
    shift = np.array([1e9, -1e9, 1e9])
    a = a.derive(a.vertices+shift, a.faces, "test", {})
    b = b.derive(b.vertices+shift, b.faces, "test", {})
    metrics, _ = evaluate_mesh(a, b, EvaluationConfig(200, 2))
    assert metrics["d95"] == pytest.approx(2.5, abs=1e-6)
    assert a.vertices[0, 0] == 1e9


def test_area_weighted_sampler_and_reproduction():
    vertices = np.array([[0., 0, 0], [1, 0, 0], [0, 2, 0], [10, 0, 0], [13, 0, 0], [10, 6, 0]])
    asset = MeshAsset(vertices, np.array([[0, 1, 2], [3, 4, 5]]))
    points, ids, weights = sample_surface(asset, 10000, 22)
    assert np.mean(ids == 1) == pytest.approx(.9, abs=.015)
    assert np.allclose(weights.sum(axis=1), 1)
    assert np.array_equal(points, sample_surface(asset, 10000, 22)[0])


def test_quality_equal_triangle():
    triangle = MeshAsset(np.array([[0., 0, 0], [1, 0, 0], [.5, np.sqrt(3)/2, 0]]), np.array([[0, 1, 2]]))
    assert triangle_measures(triangle)[1][0] == pytest.approx(1.)


def test_unknown_units_and_volume_are_not_zero():
    source = plane()
    asset = MeshAsset(source.vertices, source.faces)
    metrics, _ = evaluate_mesh(asset, asset, EvaluationConfig(100, 5))
    assert "distances_mm" not in metrics
    assert metrics["volume_change"] is None
    assert metrics["volume_status"] == "unavailable"


def test_explicit_unit_mismatch_rejected():
    source = plane()
    other = MeshAsset(source.vertices, source.faces, unit_status="confirmed", unit_name="cm", unit_to_mm=10.)
    with pytest.raises(ValueError, match="units"):
        evaluate_mesh(source, other)


@pytest.mark.parametrize("vertices,faces", [
    ([[float("nan"), 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]]),
    ([[0., 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]]),
    ([[0., 0, 0], [1, 0, 0], [0, 1, 0]], [[0., 1., 2.]]),
])
def test_invalid_inputs(vertices, faces):
    with pytest.raises(ValueError):
        MeshAsset(np.array(vertices), np.array(faces))


def test_reference_is_not_mutated_and_handoff_hash_verified(tmp_path):
    asset = plane()
    with pytest.raises(ValueError):
        asset.vertices[0, 0] = 10
    path = save_asset(asset, tmp_path/"交接 模型.npz")
    restored = load_asset(path)
    assert restored.version_id == asset.version_id
    metadata = json.loads(path.with_suffix(".json").read_text())
    metadata["geometry_sha256"] = "wrong"
    path.with_suffix(".json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="hash"):
        load_asset(path)
