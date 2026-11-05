"""Launch real Qt/VTK panel, exercise async import/repair/rollback/export, capture."""
import sys,os,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
os.environ.setdefault("QT_API","pyside6")
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtCore import QTimer
from medical_mesh.ui.preview_host import ViewerAdapter
from medical_mesh.ui.member1_panel import Member1Panel
from medical_mesh import save_mesh,load_mesh


app=QApplication(sys.argv);window=QMainWindow();viewer=ViewerAdapter(window)
root=ROOT/"results"/"gui_verification"
panel=Member1Panel(viewer,root/"session")
window.setCentralWidget(panel);window.resize(1280,900);window.show()
states=[];started=time.monotonic();stage=0


def tick():
    global stage
    try:
        if time.monotonic()-started>90:raise RuntimeError("GUI verification timed out")
        if panel.process is not None:return
        if stage==0:
            stage=1;panel.start_job("load",input_path=str(ROOT/"data"/"damaged"/"duplicate.stl"));return
        if stage==1:
            assert panel.asset is not None
            assert panel.diagnosis["metrics"]["duplicate_face_count"]==1
            states.append("async_import_and_diagnosis_passed")
            panel.defects.item(0).setSelected(True)
            panel.highlight()
            viewer.plotter.screenshot(str(root/"duplicate_highlight.png"))
            window.grab().save(str(root/"01_import_diagnosis.png"))
            stage=2;panel.start_job("repair",parameters={"remove_duplicates":True});return
        if stage==2:
            assert panel.pending_review is not None
            assert panel.store.current_version==panel.asset.version
            assert panel.diagnosis["metrics"]["duplicate_face_count"]==0
            panel.accept_preview()
            states.append("async_repair_and_version_commit_passed")
            window.grab().save(str(root/"02_repaired.png"))
            save_mesh(panel.asset,root/"exported.stl")
            assert len(load_mesh(root/"exported.stl").faces)==960
            states.append("export_roundtrip_passed")
            stage=3;panel.rollback();return
        if stage==3:
            assert panel.diagnosis["metrics"]["duplicate_face_count"]==1
            states.append("rollback_and_highlight_rebinding_passed")
            stage=4;panel.start_job("load",input_path=str(ROOT/"data"/"medical"/"FMA7197.stl"));return
        if stage==4:
            assert len(panel.asset.faces)==19416
            states.append("medical_mesh_render_passed")
            window.grab().save(str(root/"03_medical_liver.png"))
            stage=5;panel.start_job("diagnose");panel.cancel();return
        if stage==5:
            assert len(panel.asset.faces)==19416
            assert json.loads((panel.job_root/"result.json").read_text(encoding="utf-8"))["status"]=="cancelled"
            states.append("cancel_preserves_current_version_passed")
            stage=6;panel.start_job("diagnose");panel._timeout();return
        if stage==6:
            assert len(panel.asset.faces)==19416
            assert json.loads((panel.job_root/"result.json").read_text(encoding="utf-8"))["status"]=="failed"
            states.append("timeout_preserves_current_version_passed")
            stage=7;panel.start_job("load",input_path=str(root/"nonexistent.stl"));return
        if stage==7:
            assert len(panel.asset.faces)==19416
            assert json.loads((panel.job_root/"result.json").read_text(encoding="utf-8"))["status"]=="failed"
            states.append("invalid_input_preserves_current_version_passed")
            (root/"verification.json").write_text(json.dumps({"status":"completed","checks":states},indent=2),encoding="utf-8")
            print("GUI verification passed:",states,flush=True)
            timer.stop();viewer.plotter.close();window.close();app.quit()
    except Exception as e:
        print("GUI verification FAILED:",repr(e),flush=True)
        (root/"verification.json").write_text(json.dumps({"status":"failed","checks":states,"error":repr(e)},indent=2),encoding="utf-8")
        timer.stop();viewer.plotter.close();window.close();app.exit(1)


timer=QTimer();timer.timeout.connect(tick);timer.start(100)
raise SystemExit(app.exec())
