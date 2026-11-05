"""GUI checks for split proposals, project-history import, progress and cancellation."""
import json
import os
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.environ.setdefault('QT_API','pyside6')
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtCore import QTimer
from medical_mesh.ui.preview_host import ViewerAdapter
from medical_mesh.ui.member1_panel import Member1Panel
from medical_mesh.core.project_bundle import save_project
from medical_mesh.core.versions import VersionStore
from medical_mesh.core.boundary_roles import BoundaryRoles

out=ROOT/'results/delivery_verification';out.mkdir(exist_ok=True)
app=QApplication(sys.argv);window=QMainWindow();viewer=ViewerAdapter(window)
panel=Member1Panel(viewer,out/'sessions'/uuid.uuid4().hex);window.setCentralWidget(panel);window.resize(1500,1050);window.show()
stage=0;checks=[];start=time.monotonic();accepted=None;cancelled_version=None;cancel_time=None


def finish(error=None):
    timer.stop();(out/'verification.json').write_text(json.dumps(dict(status='failed' if error else 'completed',checks=checks,error=error),ensure_ascii=False,indent=2),encoding='utf-8')
    print(checks,'error:',error,flush=True);viewer.other_plotter.close();viewer.plotter.close();window.close();app.exit(1 if error else 0)


def tick():
    global stage,accepted,cancelled_version,cancel_time
    try:
        if time.monotonic()-start>180:raise RuntimeError('GUI verification timed out')
        if stage==7 and panel.process is not None:
            if (panel.job_root/'progress.json').exists():
                panel.update_progress();assert '后台阶段' in panel.task_stage.text()
                checks.append('real_worker_phase_visible_in_gui');cancel_time=time.monotonic();panel.cancel();stage=8
            return
        if panel.process is not None:return
        if stage==0:
            stage=1;panel.start_job('load',input_path=str(ROOT/'data/reference/bowtie_vertex.npz'));return
        if stage==1:
            stage=2;panel.request_suggestions();return
        if stage==2:
            index=next(i for i,p in enumerate(panel.suggestions) if p.get('split_vertex_ids')==[0])
            panel.suggestion_choice.setCurrentIndex(index+1);panel.apply_suggestion()
            assert panel.split_ids.text()=='0' and not panel.delete_ids.text()
            stage=3;panel.repair();return
        if stage==3:
            assert panel.pending_review and panel.diagnosis['metrics']['non_manifold_vertex_count']==0
            panel.accept_preview();accepted=panel.asset.version
            save_project(out/'verified_project.m3d',panel.asset,panel.diagnosis,
                         panel.boundary_roles.mapping(panel.asset,panel.diagnosis),panel.store)
            checks.append('vertex_split_proposal_previews_and_accepts_without_deletion')
            # Simulate a fresh session store, not an already populated version history.
            panel.root=out/'restored'/uuid.uuid4().hex;panel.store=VersionStore(panel.root/'versions')
            panel.boundary_roles=BoundaryRoles(panel.root/'boundary_roles.json')
            stage=4;panel.start_job('load',input_path=str(out/'verified_project.m3d'));return
        if stage==4:
            assert panel.asset.version==accepted
            assert (panel.store.root/(panel.asset.parent_version+'.npz')).exists()
            assert 'diagnosis_before' in json.loads((panel.store.root/(accepted+'.result.json')).read_text(encoding='utf-8'))
            assert json.loads((panel.store.root/(accepted+'.review.json')).read_text(encoding='utf-8'))['decision']=='accepted'
            checks.append('project_import_restores_current_snapshot_and_parent_history')
            stage=5;panel.rollback();return
        if stage==5:
            assert panel.asset.version!=accepted and panel.diagnosis['metrics']['non_manifold_vertex_count']==1
            checks.append('imported_project_can_rollback_to_real_parent_geometry')
            stage=6
        if stage==6:
            cancelled_version=panel.asset.version
            stage=7;panel.start_job('load',input_path=str(ROOT/'results/extended_validation/large_100k_input.npz'));return
        if stage==8:
            assert panel.asset.version==cancelled_version and panel.store.current_version==cancelled_version
            assert json.loads((panel.job_root/'result.json').read_text(encoding='utf-8'))['status']=='cancelled'
            assert time.monotonic()-cancel_time<3
            checks.append('cancel_large_job_preserves_accepted_version_and_pointer')
            stage=9;panel.start_job('load',input_path=str(ROOT/'results/extended_validation/large_100k_input.npz'));return
        if stage==9:
            assert len(panel.asset.faces)>100000,('faces',len(panel.asset.faces),panel.log.toPlainText())
            assert viewer.display_mesh.n_cells<len(panel.asset.faces),('LOD',viewer.display_mesh.n_cells)
            assert '视图简化' in panel.display_info.text(),('notice',panel.display_info.text())
            panel.pick_boundary.setChecked(True)
            assert viewer.plotter.actors['base_mesh'].mapper.dataset.n_cells==len(panel.asset.faces),('pick',viewer.plotter.actors['base_mesh'].mapper.dataset.n_cells)
            panel.pick_boundary.setChecked(False)
            assert viewer.plotter.actors['base_mesh'].mapper.dataset.n_cells==viewer.display_mesh.n_cells,('restore',viewer.plotter.actors['base_mesh'].mapper.dataset.n_cells,viewer.display_mesh.n_cells,viewer.local_view)
            window.grab().save(str(out/'large_mesh_display.png'))
            checks.append('large_mesh_display_is_simplified_but_picking_uses_exact_cells')
            finish()
    except Exception as error:finish(repr(error))


timer=QTimer();timer.timeout.connect(tick);timer.start(100)
raise SystemExit(app.exec())
