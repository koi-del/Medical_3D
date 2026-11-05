"""Real widgets + QProcess + FreeCAD end-to-end acceptance. No conversion mocks."""
import os
os.environ["QT_API"] = "pyside6"
from pathlib import Path
import sys
import json
import traceback
import html
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from medical_mesh.ui.bootstrap import configure_qt
configure_qt()
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from medical_mesh.ui.main_window import MainWindow
from medical_mesh.core.model import write_json

root = Path(__file__).resolve().parents[1]
output = root/"runs/gui_cad_smoke"
output.mkdir(parents=True, exist_ok=True)
configure_qt()
app = QApplication([]); app.setStyle("Fusion")
window = MainWindow(root); window.show(); window.load_demo()
version, geometry = window.current_asset.version_id, window.current_asset.geometry_hash
fixture = root/"runs/cad_validation_50k/fixtures/sphere"
completed, failures, validations = [], [], []
queue = [("direction", a, b) for a,b in (("stl","step"),("stl","igs"),("step","stl"),("step","igs"),("igs","stl"),("igs","step"))]
queue += [("corrupt", "step", "igs"), ("cancel", "step", "stl"), ("optimize", None, None), ("candidate", None, "step")]
active = None
heartbeat = 0

def tick():
    global heartbeat
    heartbeat += 1
pulse = QTimer(); pulse.timeout.connect(tick); pulse.start(40)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def abort(error):
    failures.append(str(error)); traceback.print_exc()
    write_json(output/"verification.json", {"status":"failed", "error":str(error), "completed":completed})
    window.jobs.cancel()
    QTimer.singleShot(1000, lambda: app.exit(2))


def start_next():
    global active
    try:
        if not queue:
            finish_suite(); return
        active = queue.pop(0)
        kind, source, target = active
        print("START", active, flush=True)
        if kind == "optimize":
            window.tabs.setCurrentWidget(window.pages["optimization"])
            window.samples.setValue(1000)
            QTest.mouseClick(window.run_button, Qt.LeftButton)
            check(window.jobs.busy, "optimization not submitted")
            return
        window.tabs.setCurrentWidget(window.cad)
        cad = window.cad
        cad.output_root.setText(str(output/"jobs"))
        cad.samples.setValue(50000)
        if kind == "candidate":
            check(window.current_candidate is not None, "no selected optimization preview")
            cad.mode.setCurrentIndex(2)
        else:
            cad.mode.setCurrentIndex(0)
            path = fixture/("source."+source)
            if kind == "corrupt":
                path = output/"corrupt.step"; path.write_text("THIS IS NOT STEP\n")
            # Exercise file button and its dialog result, not only the worker API.
            original = QFileDialog.getOpenFileName
            QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(path), ""))
            try:
                QTest.mouseClick(cad.browse, Qt.LeftButton)
            finally:
                QFileDialog.getOpenFileName = original
            if source == "stl":
                cad.units.setCurrentIndex(0)
                check(not cad.run_button.isEnabled(), "unknown STL unit was accepted")
                check("单位" in cad.validation.text(), "unit explanation missing")
                cad.units.setCurrentIndex(1)
            check(source not in [cad.target.itemData(i) for i in range(cad.target.count())], "same-format target offered")
        cad.target.setCurrentIndex(cad.target.findData(target))
        check(cad.run_button.isEnabled(), cad.validation.text())
        QTest.mouseClick(cad.run_button, Qt.LeftButton)
        check(window.jobs.busy, "CAD job not submitted")
        check(not cad.run_button.isEnabled() and not window.run_button.isEnabled(), "concurrent submit allowed")
        check(window.conversion_results.result is None, "stale result during new job")
        check(not window.report_button.isEnabled(), "stale report button during new job")
        if kind == "cancel":
            QTimer.singleShot(250, lambda: QTest.mouseClick(window.cancel_button, Qt.LeftButton))
    except Exception as error:
        abort(error)


def received(result):
    try:
        kind, source, target = active
        check(not window.jobs.busy, "job manager remained busy")
        check(window.current_asset.version_id == version and window.current_asset.geometry_hash == geometry, "reference changed")
        check(window.report_button.isEnabled(), "report missing")
        QTest.mouseClick(window.report_button, Qt.LeftButton)
        check(window.workspace.currentWidget() is window.report_viewer, "report opened outside window")
        text = window.report_viewer.browser.toPlainText()
        check(result["status"] in text, "HTML report did not show current status")
        check(json.loads(window.report_viewer.raw.toPlainText())["run_id"] == result["run_id"], "wrong raw report")
        if kind == "optimize":
            check(result["decision"] == "needs_review", "candidate was auto-accepted")
            check(window.current_candidate is not None, "candidate not selected")
        elif kind in ("corrupt", "cancel"):
            check(result["status"] == ("failed" if kind == "corrupt" else "cancelled"), result)
            check(window.conversion_results.result["status"] == result["status"], "stale successful summary")
            check(not window.viewer.assets, "old successful preview remained after failure")
        else:
            check(result["status"] == "completed" and result["geometry_status"] == "passed", result)
            check(result["export_status"] == "written" and result["readback_status"] == "loaded", "stage incomplete")
            check(all(result["checks"].values()), "check failed")
            check(result["config"]["samples"] == 50000, "sampling differs from selected")
            check("reference_mesh" in window.viewer.plotter.renderers[0].actors, "reference preview missing")
            check("candidate_mesh" in window.viewer.plotter.renderers[1].actors, "readback preview missing")
            check(window.viewer.assets[0].unit_name == "mm", "preview units incorrect")
            if kind == "candidate":
                check(result["source_asset"]["lifecycle"] == "candidate_unaccepted", "candidate provenance lost")
                check(result["source_asset"]["quality_status"] == "unverified", "candidate quality promoted")
                check(window.current_candidate.metadata["quality_status"] == "unverified", "candidate mutated")
        completed.append({"case":kind, "direction":f"{source or 'candidate'}->{target}", "status":result["status"],
                          "geometry_status":result.get("geometry_status"), "output_dir":str(window.last_dir),
                          "d95_mm":result.get("metrics", {}).get("d95")})
        print("DONE", completed[-1], flush=True)
        if kind == "direction" and source == "igs" and target == "step":
            window.workspace.setCurrentWidget(window.conversion_results)
            window.grab().save(str(output/"conversion_results.png"))
            window.workspace.setCurrentWidget(window.viewer)
            window.grab().save(str(output/"model_comparison.png"))
            window.open_report()
            window.grab().save(str(output/"report_view.png"))
        QTimer.singleShot(350, start_next)
    except Exception as error:
        abort(error)


def finish_suite():
    try:
        saved = Path(completed[0]["output_dir"])/"result.json"
        window.load_saved_task(saved)
        check(window.workspace.currentWidget() is window.report_viewer, "saved report not selected")
        check(window.last_result["run_id"] == saved.parent.name, "wrong saved task")
        check(window.conversion_results.result["geometry_status"] == "passed", "saved result lost")
        check(window.current_asset.version_id == version, "history changed reference")
        fresh = MainWindow(root)
        fresh.load_saved_task(saved)
        check(fresh.current_asset is None, "history silently set a formal reference")
        check(fresh.conversion_results.result["geometry_status"] == "passed", "fresh window lost saved result")
        fresh.close()
        check(heartbeat > 100, "UI event loop did not remain responsive")
        validations.extend(["unknown_stl_unit_blocked", "same_format_excluded", "single_active_job", "failure_no_stale_result",
                            "cancel_recovered", "candidate_provenance_preserved", "reference_unchanged", "saved_report_reopened",
                            "in_window_html_and_json", "actual_readback_mesh_previews", "ui_event_loop_responsive", "fresh_window_history"])
        write_json(output/"verification.json", {"status":"passed", "cases":completed, "assertions":validations,
                                              "ui_heartbeat_count":heartbeat, "samples_per_direction":50000})
        rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(case.get(k, '—')))}</td>" for k in ("case", "direction", "status", "geometry_status", "d95_mm", "output_dir")) + "</tr>" for case in completed)
        (output/"report.html").write_text('<!doctype html><meta charset="utf-8"><h1>桌面CAD完整流程验收：通过</h1><p>六个方向全部通过；每方向50000点，实际FreeCAD回读。损坏与取消为预期失败；优化及候选转换通过流程检查。数据为合成球面。</p><table border="1" cellpadding="8"><tr><th>类型</th><th>方向</th><th>执行</th><th>几何</th><th>D95/mm</th><th>任务目录</th></tr>'+rows+'</table><p>'+html.escape(", ".join(validations))+'</p>', encoding="utf-8")
        window.close(); app.quit()
    except Exception as error:
        abort(error)

window.jobs.finished.connect(received)
QTimer.singleShot(500, start_next)
QTimer.singleShot(240000, lambda: abort(RuntimeError("suite timeout")))
exit_code = app.exec()
raise SystemExit(exit_code if len(completed) == 10 and not failures else 2)
