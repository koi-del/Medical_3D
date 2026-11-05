"""Exercise explicit candidate review and boundary picking in the real Qt panel."""
import sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtWidgets import QApplication,QMainWindow
from medical_mesh import load_mesh,detect_defects
from medical_mesh.ui.preview_host import ViewerAdapter
from medical_mesh.ui.member1_panel import Member1Panel
errors=[]
sys.excepthook=lambda kind,value,tb:errors.append(repr(value))
out=ROOT/'results'/'review_verification';out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);window=QMainWindow();viewer=ViewerAdapter(window)
panel=Member1Panel(viewer,out/'session');window.setCentralWidget(panel);window.resize(1440,1050);window.show()
checks=[];signals=[];panel.asset_changed.connect(lambda a:signals.append(a.version))


def wait():
    deadline=time.monotonic()+40
    while panel.process is not None:
        app.processEvents();time.sleep(.02)
        if time.monotonic()>deadline:raise RuntimeError('Worker timed out')
    app.processEvents()
    assert not errors,errors


try:
    panel.start_job('load',input_path=str(ROOT/'data/damaged/duplicate.npz'));wait()
    original=panel.asset;count=len(signals)
    panel.start_job('repair',parameters={'remove_duplicates':True});wait()
    assert panel.pending_review and panel.asset.version==original.version
    assert panel.store.current_version==original.version and len(signals)==count
    assert not panel.export_button.isEnabled()
    assert panel.diagnosis['metrics']['duplicate_face_count']==0
    panel.preview_side.setCurrentIndex(1);app.processEvents()
    assert panel.display_asset().version==original.version and panel.diagnosis['metrics']['duplicate_face_count']==1
    panel.preview_side.setCurrentIndex(0);app.processEvents()
    window.grab().save(str(out/'candidate_preview.png'))
    checks.append('preview_and_before_after_switch_keep_accepted_version')
    panel.discard_preview();assert panel.asset.version==original.version
    assert panel.diagnosis['metrics']['duplicate_face_count']==1 and len(signals)==count
    checks.append('discard_preserves_geometry_version_and_downstream_signals')
    panel.start_job('repair',parameters={'remove_duplicates':True});wait()
    panel.accept_preview();assert panel.pending_review is None
    assert panel.asset.parent_version==original.version and len(signals)==count+1
    assert panel.diagnosis['metrics']['duplicate_face_count']==0
    panel.rollback();wait();assert panel.asset.version==original.version
    checks.append('accept_commits_new_version_and_rollback_restores_input')
    panel.start_job('load',input_path=str(ROOT/'data/reference/open_tube.npz'));wait()
    panel.pick_boundary.setChecked(True);app.processEvents()
    boundary=panel.diagnosis['boundaries'][0];a,b=boundary['edges'][0]
    panel.select_boundary_at(panel.asset.vertices[[a,b]].mean(axis=0))
    assert [x.data(256).get('boundary') for x in panel.defects.selectedItems()]==[boundary['id']]
    checks.append('boundary_point_selection_matches_diagnosed_loop')
    panel.defects.clearSelection();viewer.set_view(0);app.processEvents()
    picked=False
    for boundary in panel.diagnosis['boundaries']:
        for a,b in boundary['edges']:
            point=panel.asset.vertices[[a,b]].mean(axis=0)
            renderer=viewer.plotter.renderer
            renderer.SetWorldPoint(*point,1);renderer.WorldToDisplay()
            x,y,_=renderer.GetDisplayPoint()
            viewer.plotter.iren.picker.Pick(x,y,0,renderer)
            app.processEvents()
            if any(item.data(256).get('boundary')==boundary['id'] for item in panel.defects.selectedItems()):
                picked=True;break
        if picked:break
    assert picked,'VTK surface picker did not select any rim'
    checks.append('actual_vtk_pick_event_selects_boundary')
    panel.opacity.setValue(45);panel.view_preset.setCurrentIndex(1);app.processEvents()
    assert abs(viewer.plotter.actors['base_mesh'].prop.opacity-.45)<1e-8
    checks.append('opacity_and_camera_presets_work')
    window.grab().save(str(out/'boundary_picking.png'))
    assert not errors,errors
    (out/'verification.json').write_text(json.dumps({'status':'completed','checks':checks},indent=2),encoding='utf-8')
    print(json.dumps(checks))
finally:
    if panel.process:panel.cancel();panel.process.waitForFinished(1000)
    viewer.plotter.close();window.close()
