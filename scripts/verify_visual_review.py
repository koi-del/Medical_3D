"""Real Qt/VTK validation of paired cameras, change overlays and patch indicators."""
import json
import os
import sys
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_API','pyside6')
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtCore import QTimer
from medical_mesh import load_mesh
from medical_mesh.core.review import CandidateReview
from medical_mesh.processing.mesh_worker import run_job
from medical_mesh.ui.preview_host import ViewerAdapter
from medical_mesh.ui.member1_panel import Member1Panel

out=ROOT/'results/visual_review_verification';out.mkdir(exist_ok=True)
app=QApplication(sys.argv);window=QMainWindow();viewer=ViewerAdapter(window)
panel=Member1Panel(viewer,out/'sessions'/uuid.uuid4().hex)
window.setCentralWidget(panel);window.resize(1500,1000);window.show()
checks=[];index=0
cases=[('hole',{'fill_boundary_ids':[0]},'change_added'),
       ('duplicate',{'remove_duplicates':True},'change_removed'),
       ('flip',{'orient_faces':True},'change_flipped'),
       ('degenerate',{'remove_degenerate':True},'change_removed')]


def tick():
    global index
    try:
        if index==len(cases):
            timer.stop()
            (out/'verification.json').write_text(json.dumps(dict(status='completed',checks=checks),ensure_ascii=False,indent=2),encoding='utf-8')
            print(checks,flush=True);viewer.other_plotter.close();viewer.plotter.close();window.close();app.quit();return
        name,parameters,actor_name=cases[index]
        job=out/'jobs'/uuid.uuid4().hex
        source=ROOT/'data/damaged'/(name+'.npz')
        before=load_mesh(source);original=before.geometry_hash()
        data=run_job(dict(operation='repair',input_path=str(source),output_dir=str(job),
                          parameters={**parameters,'check_self_intersection':True}))
        assert data['status']=='completed',data['errors']
        candidate=load_mesh(data['output_paths']['mesh'])
        panel.asset=before;panel.accepted_diagnosis=data['diagnosis_before'];panel.store.commit(before)
        panel.pending_review=CandidateReview(before,candidate,data,job)
        panel.preview_side.blockSignals(True);panel.preview_side.setCurrentIndex(0);panel.preview_side.blockSignals(False)
        panel.dual_view.setChecked(True);panel.show_changes.setChecked(True)
        panel.bind_diagnosis(data['diagnosis_after']);panel.render();panel._busy(False)
        panel.patch_summary.setText(panel.quality_text(data['metrics']['patch_quality']))
        assert viewer.comparing and viewer.other_plotter.interactor.isVisible()
        assert viewer.plotter.camera.GetAddressAsString('')==viewer.other_plotter.camera.GetAddressAsString('')
        if name=='hole':
            assert actor_name in viewer.plotter.actors
            quality=data['metrics']['patch_quality']
            assert quality['face_count']==1 and quality['seam_edge_count']==3
            assert '最小角' in panel.patch_summary.text()
            checks.append('real_worker_patch_quality_persisted_and_displayed')
        else:
            assert actor_name in (viewer.plotter.actors if name=='flip' else viewer.other_plotter.actors)
        changes=data['metrics']['changes']
        ids=changes['added_face_ids'] or changes['flipped_output_face_ids']
        panel.focus_changes()
        viewer.plotter.camera.azimuth+=12;viewer._sync_comparison()
        assert viewer.plotter.camera.position==viewer.other_plotter.camera.position
        app.processEvents()
        window.grab().save(str(out/(name+'_paired.png')))
        if name=='hole':
            viewer.save_snapshot(out/'paired_snapshot.png')
            assert (out/'paired_snapshot.png').stat().st_size>1000
            checks.append('paired_snapshot_saved')
        panel.show_changes.setChecked(False)
        assert not any(key.startswith('change_') for key in viewer.plotter.actors)
        panel.show_changes.setChecked(True)
        panel.preview_side.setCurrentIndex(1)
        if name in ('duplicate','degenerate'):assert actor_name in viewer.plotter.actors
        if name=='degenerate':assert 'change_removed_lines' in viewer.plotter.actors
        panel.dual_view.setChecked(False);assert not viewer.comparing
        assert panel.asset.geometry_hash()==original and panel.store.current_version==before.version
        panel.discard_preview()
        assert not viewer.comparing
        assert not any(key.startswith('change_') for key in viewer.plotter.actors)
        checks.append(name+'_paired_camera_overlay_toggle_and_discard_passed')
        index+=1
    except Exception as error:
        timer.stop();print('FAILED',repr(error),flush=True)
        (out/'verification.json').write_text(json.dumps(dict(status='failed',error=repr(error),checks=checks),indent=2),encoding='utf-8')
        viewer.other_plotter.close();viewer.plotter.close();window.close();app.exit(1)


timer=QTimer();timer.timeout.connect(tick);timer.start(700)
raise SystemExit(app.exec())
