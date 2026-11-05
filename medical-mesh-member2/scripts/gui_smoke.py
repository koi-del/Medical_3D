"""Real local GUI integration smoke: click run, await subprocess, capture result."""
import os
os.environ["QT_API"] = "pyside6"
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from medical_mesh.ui.bootstrap import configure_qt
configure_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from medical_mesh.ui.main_window import MainWindow
from medical_mesh.core.model import write_json

root = Path(__file__).resolve().parents[1]
configure_qt()
app = QApplication([])
app.setStyle("Fusion")
window = MainWindow(root, off_screen=False)
window.show()
window.load_demo()
reference_version = window.current_asset.version_id
completed = []

def finished(result):
    completed.append(result)
    assert result["status"] == "completed", result
    assert result["decision"] == "needs_review", result
    assert window.current_asset.version_id == reference_version
    assert window.table.rowCount() == 1
    assert "reference_mesh" in window.viewer.plotter.renderers[0].actors
    assert "candidate_mesh" in window.viewer.plotter.renderers[1].actors
    if len(completed) == 1:
        QTimer.singleShot(500, lambda: QTest.mouseClick(window.run_button, Qt.LeftButton))
        return
    def capture():
        directory = root/"runs/gui_smoke"
        directory.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(directory/"window.png"))
        write_json(directory/"verification.json", {"status": "passed", "job_status": result["status"],
            "decision": result["decision"], "reference_unchanged": True, "candidate_rows": window.table.rowCount(),
            "consecutive_jobs": len(completed), "report_directory": str(window.last_dir)})
        window.close(); app.quit()
    QTimer.singleShot(500, capture)

window.jobs.finished.connect(finished)
window.samples.setValue(1000)
QTimer.singleShot(500, lambda: QTest.mouseClick(window.run_button, Qt.LeftButton))
def watchdog():
    if len(completed) < 2:
        window.jobs.cancel("timeout")
        app.exit(3)
QTimer.singleShot(60000, watchdog)
code = app.exec()
raise SystemExit(code if len(completed) == 2 else 3)
