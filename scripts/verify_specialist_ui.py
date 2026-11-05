"""Exercise new curve mode through the real Qt/VTK preview and worker path."""
import json
import os
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_API','pyside6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QMainWindow,QFileDialog
from medical_mesh.ui.preview_host import ViewerAdapter
from medical_mesh.ui.member1_panel import Member1Panel

out=ROOT/'results/specialist_ui_verification';out.mkdir(exist_ok=True)
app=QApplication(sys.argv);window=QMainWindow();viewer=ViewerAdapter(window)
panel=Member1Panel(viewer,out/'sessions'/uuid.uuid4().hex)
window.setCentralWidget(panel);window.resize(1500,1000);window.show()
stage=0;started=time.monotonic();checks=[];input_version=None


def finish(error=None):
    timer.stop()
    (out/'verification.json').write_text(json.dumps(dict(status='failed' if error else 'completed',
        checks=checks,error=error),ensure_ascii=False,indent=2),encoding='utf-8')
    print(checks,error,flush=True)
    viewer.other_plotter.close();viewer.plotter.close();window.close();app.exit(1 if error else 0)


def tick():
    global stage,input_version
    try:
        if time.monotonic()-started>90:raise RuntimeError('专项GUI验证超时')
        if panel.process is not None:return
        if stage==0:
            stage=1;panel.start_job('load',input_path=str(ROOT/'results/e3d_complex/inputs/c_h2.stl'));return
        if stage==1:
            assert panel.asset is not None
            boundaries=panel.diagnosis['boundaries'];inner=min(boundaries,key=lambda b:b['span'])
            panel.boundary_roles.mark(panel.asset,[b for b in boundaries if b['id']!=inner['id']],'natural')
            panel.boundary_roles.mark(panel.asset,[inner],'repair_target')
            panel.bind_diagnosis(panel.diagnosis)
            index=panel.hole_method.findData('surface');assert index>=0;panel.hole_method.setCurrentIndex(index)
            input_version=panel.asset.version
            checks.append('new_curve_mode_available_and_explicit_roles_saved')
            stage=2;panel.repair();assert panel.self_check.isChecked();return
        if stage==2:
            assert panel.pending_review is not None,panel.log.toPlainText()
            assert panel.asset.version==input_version
            assert panel.diagnosis['metrics']['topology_passed']
            assert panel.diagnosis['metrics']['boundary_loop_count']==1
            assert panel.diagnosis['self_intersection']['status']=='verified'
            checks.append('real_worker_high_curvature_candidate_passes_without_committing')
            window.grab().save(str(out/'high_curvature_preview.png'))
            panel.accept_preview();assert panel.asset.version!=input_version
            checks.append('accept_preview_commits_verified_candidate')
            stage=3;panel.start_job('load',input_path=str(ROOT/'data/reference/bowtie_vertex.npz'));return
        if stage==3:
            panel.split_ids.setText('0');panel.self_check.setChecked(True)
            stage=4;panel.repair();return
        if stage==4:
            assert panel.pending_review is not None,panel.log.toPlainText()
            panel.accept_preview()
            destination=out/'pin.stlset.zip'
            original_dialog=QFileDialog.getSaveFileName
            QFileDialog.getSaveFileName=lambda *args,**kwargs:(str(destination),'分壳STL集合 (*.stlset.zip)')
            try:panel.export()
            finally:QFileDialog.getSaveFileName=original_dialog
            import zipfile
            with zipfile.ZipFile(destination) as archive:
                manifest=json.loads(archive.read('manifest.json'))
            assert len(manifest['shells'])==2
            assert all(s['diagnosis']['quality_status']=='verified_closed_surface' for s in manifest['shells'])
            checks.append('real_export_action_writes_two_verified_separate_stl_shells')
            finish()
    except Exception as error:finish(str(error))


timer=QTimer();timer.timeout.connect(tick);timer.start(150)
sys.exit(app.exec())
