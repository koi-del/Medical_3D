import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest

from medical_mesh.cad.runner import (effective_config, validate_config, run_worker,
                                      probe_freecad, conversion_checks)
from medical_mesh.core.model import MeshAsset
from medical_mesh.evaluation import evaluate_mesh, EvaluationConfig


@pytest.mark.parametrize("field,value", [("timeout_seconds", 0), ("d95_mm", float("nan")),
                                        ("samples", True), ("readback_angular_deflection_rad", 4.)])
def test_invalid_cad_configuration(field, value):
    config = effective_config({field: value})
    with pytest.raises(ValueError):
        validate_config(config)


def test_fine_tessellation_must_be_finer():
    with pytest.raises(ValueError, match="coarser"):
        validate_config(effective_config({"readback_linear_deflection_mm": .1}))


def test_stale_worker_result_is_rejected(tmp_path):
    fake = tmp_path/"fake.py"
    fake.write_text('import json,os\nfrom pathlib import Path\nr=json.loads(Path(os.environ["MEDICAL_MESH_CAD_JOB"]).read_text())\nPath(r["result_path"]).write_text(json.dumps({"status":"completed","request_id":"stale","mode":"probe"}))\n')
    with pytest.raises(RuntimeError, match="stale"):
        run_worker({"executable": sys.executable, "arguments": [str(fake)]}, {"mode": "probe"}, tmp_path, "stale")


def test_native_worker_timeout_is_not_success(tmp_path):
    fake = tmp_path/"slow.py"
    fake.write_text("import time\ntime.sleep(3)\n")
    with pytest.raises(subprocess.TimeoutExpired):
        run_worker({"executable": sys.executable, "arguments": [str(fake)], "timeout_seconds": .02},
                   {"mode": "probe"}, tmp_path, "slow")


def test_same_bbox_mirror_detected_by_surface_distance():
    a = MeshAsset(np.array([[0., 0, 0], [2, 0, 0], [0, 1, 0]]), np.array([[0, 1, 2]]))
    xyz = a.vertices.copy(); xyz[:, 0] = 2-xyz[:, 0]
    b = a.derive(xyz, a.faces, "reflection", {})
    metrics, _ = evaluate_mesh(a, b, EvaluationConfig(2000, 17))
    checks, _ = conversion_checks(metrics, metrics, 0., effective_config())
    assert checks["coordinate_bbox"]
    assert not checks["d95"]
    assert not checks["sampled_max"]


def test_real_freecad_periodic_iges_roundtrip(tmp_path):
    if probe_freecad()["status"] == "unavailable":
        pytest.skip("FreeCAD not installed; real CAD test must be run on target platform")
    config = effective_config()
    runtime = run_worker(config, {"mode": "probe"}, tmp_path, "runtime")
    assert runtime["meshpart_available"]
    fixtures = run_worker(config, {"mode": "fixtures", "fixture_dir": str(tmp_path/"fixtures")}, tmp_path, "fixtures")
    sphere = next(x for x in fixtures["manifest"] if x["case"] == "sphere")
    result = run_worker(config, {"mode": "inspect", "input_path": sphere["paths"]["igs"], "source_format": "igs",
                                "linear_deflection_mm": .01, "angular_deflection_rad": .1}, tmp_path, "roundtrip")
    assert result["pid"] != runtime["pid"]
    assert result["valid"]
    assert result["mesh_faces"] > 0
    assert result["area_mm2"] == pytest.approx(4*np.pi*25, rel=1e-8)
    assert np.allclose(result["bbox_mm"], [[9, -13, 15], [19, -3, 25]], atol=.01, rtol=0)
