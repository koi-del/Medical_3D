"""Exercise role marking and async repair proposals in the real Qt/VTK panel."""
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_API','pyside6')
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtCore import QTimer
from medical_mesh.ui.preview_host import ViewerAdapter
from medical_mesh.ui.member1_panel import Member1Panel

out=ROOT/'results/guided_repair_verification'
out.mkdir(exist_ok=True)
app=QApplication(sys.argv);window=QMainWindow();viewer=ViewerAdapter(window)
# Each run uses its own session so previous user decisions remain untouched.
import uuid
panel=Member1Panel(viewer,out/'sessions'/uuid.uuid4().hex)
window.setCentralWidget(panel);window.resize(1360,960);window.show()
stage=0;started=time.monotonic();checks=[];input_version=None


def select_boundary(bid=0):
    for index in range(panel.defects.count()):
        item=panel.defects.item(index)
        if item.data(256).get('boundary')==bid:
            panel.defects.clearSelection();item.setSelected(True);return
    raise AssertionError('Missing boundary 0')


def finish(error=None):
    timer.stop()
    (out/'verification.json').write_text(json.dumps(dict(
        status='failed' if error else 'completed',checks=checks,error=error),
        ensure_ascii=False,indent=2),encoding='utf-8')
    print('GUI checks:',checks,'error:',error,flush=True)
    viewer.plotter.close();window.close();app.exit(1 if error else 0)


def tick():
    global stage,input_version
    try:
        if time.monotonic()-started>100:raise RuntimeError('GUI test timeout')
        if panel.process is not None:return
        if stage==0:
            stage=1;panel.start_job('load',input_path=str(ROOT/'data/damaged/hole.npz'));return
        if stage==1:
            assert panel.asset is not None
            select_boundary();assert viewer.local_view
            checks.append('selection_automatically_focuses_real_geometry')
            panel.boundary_role.setCurrentIndex(panel.boundary_role.findData('natural'))
            panel.mark_boundary_role()
            assert panel.boundary_roles.mapping(panel.asset,panel.diagnosis)=={'0':'natural'}
            assert '天然开口' in panel.defects.item(panel.defects.count()-1).text()
            checks.append('natural_opening_role_persisted_and_visible')
            select_boundary()
            panel.boundary_role.setCurrentIndex(panel.boundary_role.findData('repair_target'))
            panel.mark_boundary_role()
            input_version=panel.asset.version
            stage=2;panel.repair();return
        if stage==2:
            assert panel.pending_review is not None
            assert panel.asset.version==input_version
            assert panel.diagnosis['metrics']['boundary_loop_count']==0
            window.grab().save(str(out/'hole_candidate.png'))
            panel.discard_preview()
            assert panel.diagnosis['metrics']['boundary_loop_count']==1
            assert panel.boundary_roles.mapping(panel.asset,panel.diagnosis)=={'0':'repair_target'}
            checks.append('marked_target_previews_without_commit_and_discard_restores_role')
            stage=3;panel.start_job('load',input_path=str(ROOT/'data/damaged/non_manifold_edge.npz'));return
        if stage==3:
            input_version=panel.asset.version
            stage=4;panel.request_suggestions();return
        if stage==4:
            assert panel.asset.version==input_version and panel.pending_review is None
            assert len(panel.suggestions)>=2
            assert panel.suggestion_choice.currentIndex()==0 and not panel.delete_ids.text()
            checks.append('async_proposals_show_ambiguity_and_do_not_auto_select_or_commit')
            panel.suggestion_choice.setCurrentIndex(1);panel.apply_suggestion()
            assert panel.delete_ids.text()=='960'
            window.grab().save(str(out/'nonmanifold_proposal.png'))
            stage=5;panel.repair();return
        if stage==5:
            assert panel.pending_review is not None
            assert panel.asset.version==input_version
            assert panel.diagnosis['metrics']['non_manifold_edge_count']==0
            panel.accept_preview()
            assert panel.asset.version!=input_version
            assert panel.diagnosis['metrics']['boundary_loop_count']==0
            assert len(panel.asset.faces)==960
            checks.append('selected_proposal_requires_preview_then_explicit_acceptance')
            from medical_mesh import save_mesh
            from medical_mesh.data.optimization_cases import quadric_annulus
            path=out/'quadric_annulus.npz';save_mesh(quadric_annulus(),path)
            stage=6;panel.start_job('load',input_path=str(path));return
        if stage==6:
            inner=min(panel.diagnosis['boundaries'],key=lambda b:b['span'])['id']
            select_boundary(inner)
            panel.boundary_role.setCurrentIndex(panel.boundary_role.findData('repair_target'))
            panel.mark_boundary_role()
            panel.hole_method.setCurrentIndex(panel.hole_method.findData('quadric'))
            panel.self_check.setChecked(False)
            stage=7;panel.repair();return
        if stage==7:
            assert panel.self_check.isChecked()
            assert panel.pending_review is not None
            assert panel.diagnosis['metrics']['boundary_loop_count']==1
            assert panel.diagnosis['self_intersection']['face_ids']==[]
            assert panel.diagnosis['metrics']['vertex_count']==73
            window.grab().save(str(out/'curved_candidate.png'))
            panel.discard_preview()
            assert panel.diagnosis['metrics']['boundary_loop_count']==2
            checks.append('experimental_curved_preview_forces_self_check_and_preserves_other_rim')
            finish()
    except Exception as error:finish(repr(error))


timer=QTimer();timer.timeout.connect(tick);timer.start(100)
raise SystemExit(app.exec())
