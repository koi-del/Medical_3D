import json
import sys
from pathlib import Path
import pytest
from medical_mesh.core.model import save_asset
from medical_mesh.fixtures import plane
from medical_mesh.jobs.worker import dispatch
from medical_mesh.reporting import render_report
from medical_mesh.cad import convert_file


def test_failed_request_keeps_original_and_report(tmp_path):
    source = save_asset(plane(), tmp_path/"source.npz")
    result = dispatch({"operation": "evaluate", "input_path": str(source),
                       "candidate_path": str(tmp_path/"missing.npz"), "output_dir": str(tmp_path/"job")})
    assert result["status"] == "failed"
    assert source.exists()
    assert (tmp_path/"job/report.html").exists()


def test_report_escapes_errors_and_keeps_null(tmp_path):
    render_report({"status": "failed", "errors": ["<script>test</script>"], "volume_change": None}, tmp_path)
    text = (tmp_path/"report.html").read_text()
    assert "<script>test</script>" not in text
    assert "&lt;script&gt;" in text
    assert json.loads((tmp_path/"result.json").read_text())["volume_change"] is None


def test_missing_freecad_is_not_conversion_success(tmp_path):
    source = tmp_path/"source.stl"; source.write_text("not a real STL")
    result = convert_file(source, "step", {"executable": str(tmp_path/"missingFreeCAD")}, tmp_path/"cad")
    assert result["status"] == "unavailable"
    assert result["export_status"] == "not_run"
    assert result["geometry_status"] == "not_run"


def test_qprocess_worker_and_cancellation_recovery(tmp_path):
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    from medical_mesh.jobs.qt_manager import JobManager
    app = QCoreApplication.instance() or QCoreApplication([])
    manager = JobManager()
    results = []
    loop = QEventLoop()
    manager.finished.connect(lambda result: (results.append(result), loop.quit()))
    # Startup and module imports take long enough that cancelling immediately is deterministic.
    manager.submit({"operation": "probe", "output_dir": str(tmp_path/"cancelled")})
    QTimer.singleShot(100, manager.cancel)
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    assert results and results[-1]["status"] == "cancelled"
    assert not manager.busy
    manager.submit({"operation": "probe", "output_dir": str(tmp_path/"recovery")})
    QTimer.singleShot(30000, loop.quit)
    loop.exec()
    assert results[-1]["status"] == "completed"
    assert results[-1]["run_id"] == "recovery"


def test_asset_conversion_snapshot_units_and_provenance(tmp_path, monkeypatch):
    import numpy as np
    import trimesh
    import medical_mesh.cad
    from medical_mesh.core.model import MeshAsset, load_asset
    original = plane()
    asset = MeshAsset(original.vertices, original.faces, unit_status="confirmed", unit_name="cm", unit_to_mm=10.,
                      metadata={"lifecycle":"candidate_unaccepted", "quality_status":"unverified"})
    source = save_asset(asset, tmp_path/"candidate.npz")
    def convert(input_path, target, config, directory, unit, progress):
        mesh = trimesh.load_mesh(input_path, process=False)
        assert unit == "mm" and target == "step"
        assert np.allclose(mesh.bounds, [asset.vertices.min(axis=0)*10, asset.vertices.max(axis=0)*10])
        return {"status":"completed", "operation":"convert", "quality_status":"passed"}
    monkeypatch.setattr(medical_mesh.cad, "convert_file", convert)
    result = dispatch({"operation":"convert", "asset_input_path":str(source), "target_format":"step",
                       "output_dir":str(tmp_path/"job")})
    assert result["status"] == "completed"
    assert result["source_asset"]["quality_status"] == "unverified"
    assert result["source_asset"]["lifecycle"] == "candidate_unaccepted"
    assert result["source_asset"]["version_id"] == asset.version_id
    assert load_asset(source).geometry_hash == asset.geometry_hash
    assert load_asset(source).metadata["quality_status"] == "unverified"


def test_unknown_unit_asset_conversion_is_rejected(tmp_path):
    from medical_mesh.core.model import MeshAsset
    original = plane()
    source = save_asset(MeshAsset(original.vertices, original.faces), tmp_path/"unknown.npz")
    result = dispatch({"operation":"convert", "asset_input_path":str(source), "target_format":"step",
                       "output_dir":str(tmp_path/"job")})
    assert result["status"] == "failed"
    assert "单位" in result["errors"][0]
    assert not (tmp_path/"job/source_asset_mm.stl").exists()


def test_report_write_error_does_not_leave_job_busy(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    import medical_mesh.reporting
    from medical_mesh.jobs.qt_manager import JobManager
    app = QCoreApplication.instance() or QCoreApplication([])
    manager = JobManager(); loop = QEventLoop(); results = []
    manager.finished.connect(lambda result: (results.append(result), loop.quit()))
    def fail(*args):
        raise OSError("simulated read-only report directory")
    monkeypatch.setattr(medical_mesh.reporting, "render_report", fail)
    manager.submit({"operation":"probe", "output_dir":str(tmp_path/"job")})
    QTimer.singleShot(20000, loop.quit); loop.exec()
    assert results and not manager.busy
    assert results[0]["status"] == "failed"
    assert "report_error" in results[0]
