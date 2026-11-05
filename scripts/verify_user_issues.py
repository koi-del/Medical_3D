"""Reproduce the reported interaction failures against real widgets and workers."""
import os,sys,time,json,uuid
import numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.environ.setdefault('QT_API','pyside6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from medical_mesh.ui.workbench import Workbench
out=ROOT/'results/user_issue_verification';out.mkdir(exist_ok=True)
app=QApplication([]);w=Workbench(ROOT,out/'sessions'/uuid.uuid4().hex);w.root=out;w.numerical.root=out;w.show()
r=w.repair;n=w.numerical;stage=0;started=time.monotonic();checks=[]
def finish(error=None):
    timer.stop();(out/'verification.json').write_text(json.dumps(dict(status='completed' if error is None else 'failed',checks=checks,error=error),ensure_ascii=False,indent=2),encoding='utf-8');print(checks,error,flush=True)
    w.close();app.exit(0 if error is None else 1)
def load(path):r.start_job('load',input_path=str(ROOT/path))
def tick():
    global stage
    try:
        if time.monotonic()-started>240:raise RuntimeError('issue verification timeout')
        if r.process is not None or n.jobs.busy:return
        if stage==0:
            before=w.viewport.width();w.left_sidebar.toggle_collapse();w.right_sidebar.toggle_collapse();app.processEvents();QTest.qWait(100)
            assert w.viewport.width()>before+300,(before,w.viewport.width())
            w.grab().save(str(out/'01_collapsed_viewport.png'))
            w.left_sidebar.set_open(True);w.right_sidebar.set_open(True);app.processEvents();checks.append('collapsed_sides_release_width_to_canvas')
            load('data/damaged/duplicate.npz');stage=1;return
        if stage==1:
            assert w.model_name.text()=='duplicate.npz',w.model_name.text()
            r.defects.setCurrentRow(0);camera=np.asarray(list(w.viewer.plotter.camera_position),dtype=float);r.focus_selected(manual=True)
            assert not np.allclose(camera,np.asarray(list(w.viewer.plotter.camera_position),dtype=float)),'focus did not move or zoom camera'
            text=r.selection_help.text();r.focus_selected(manual=True)
            assert r.selection_help.text()==text and text.count('局部视图：')==1
            checks.append('focus_help_is_idempotent')
            r.clean_duplicates.setChecked(True);r.repair();stage=2;return
        if stage==2:
            assert r.pending_review and r.pending_review.result['diagnosis_after']['metrics']['duplicate_face_count']==0
            w.refresh_state();assert r.controls_scroll.isEnabled()
            scroll=r.controls_scroll.verticalScrollBar();scroll.setValue(scroll.maximum());assert scroll.value()==scroll.maximum()
            assert n.report_viewer.current_path and n.report_viewer.current_path.exists()
            assert '完整记录' not in n.report_viewer.browser.toPlainText()
            checks.append('duplicate_removed_scroll_readable_and_repair_report_generated')
            r.accept_preview();w.refresh_state();assert w.previous_asset is not None and w.before_after_button.isEnabled()
            w.show_accepted_comparison();assert n.viewer.last_comparison[0].version_id!=n.viewer.last_comparison[1].version_id
            checks.append('accepted_before_after_objects_available')
            load('data/damaged/flip.npz');stage=3;return
        if stage==3:
            assert w.model_name.text()=='flip.npz',w.model_name.text()
            assert n.optimization_result is None and n.table.rowCount()==0
            r.defects.setCurrentRow(2);assert r.conflict_edge_choice.count()==3
            w.grab().save(str(out/'02_flip_single_edge.png'));checks.append('same_asset_id_new_source_name_and_edge_selector')
            load('data/reference/open_tube.npz');stage=4;return
        if stage==4:
            assert r.boundary_table.rowCount()==2
            c=r.boundary_table.cellWidget(0,1);c.setCurrentIndex(c.findData('natural'))
            c=r.boundary_table.cellWidget(1,1);c.setCurrentIndex(c.findData('repair_target'))
            roles=r.boundary_roles.mapping(r.asset,r.diagnosis);assert roles['0']=='natural' and roles['1']=='repair_target',roles
            checks.append('boundary_roles_independent_without_multi_selection')
            r.repair();stage=4.5;return
        if stage==4.5:
            assert r.pending_review and r.pending_review.result['diagnosis_after']['metrics']['boundary_loop_count']==1
            checks.append('fill_one_pipe_end_preserves_other_natural_opening')
            r.discard_preview()
            load('data/damaged/hole.npz');stage=5;return
        if stage==5:
            before=r.boundary_roles.mapping(r.asset,r.diagnosis);r.suggest_boundary_roles();assert r.boundary_roles.mapping(r.asset,r.diagnosis)==before
            r.confirm_boundary_advice();assert r.boundary_roles.mapping(r.asset,r.diagnosis)['0']=='repair_target'
            checks.append('small_hole_advice_requires_explicit_confirmation')
            load('data/reference/sphere.npz');stage=6;return
        if stage==6:
            w.set_step('optimize');n.search.setChecked(False);n.operation.setCurrentIndex(n.operation.findData('qem'));n.target_mode.setCurrentIndex(0);n.ratio.setValue(20)
            n.limit_d95.setValue(.001);n.limit_max.setValue(.003);n.limit_area.setValue(.01);n.samples.setValue(300);n.run_optimization();stage=7;return
        if stage==7:
            assert n.last_result['decision']=='rejected',n.last_result
            assert n.current_candidate is not None and len(n.current_candidate.faces)==192
            assert len(r.asset.faces)==960 and '192' in w.metric_summary.text()
            checks.append('rejected_candidate_still_displayed_with_current_metrics')
            w.set_step('evaluate');w.evaluation_path.setText(str(ROOT/'data/reference/sphere.npz'));w.evaluation_samples.setValue(1000);w.evaluate_external();stage=8;return
        if stage==8:
            w.refresh_state();assert n.last_result['operation']=='evaluate' and not n.table.isVisible(),('old table',n.last_result['operation'],n.table.isVisible(),w.current_result_operation)
            assert '192' not in w.metric_summary.text(),w.metric_summary.text()
            assert n.report_viewer.tabs.count()==1 and '完整记录' not in n.report_viewer.browser.toPlainText(),('report',n.report_viewer.tabs.count(),n.report_viewer.browser.toPlainText()[-500:])
            n.report_viewer.show_fullscreen();app.processEvents();assert n.report_viewer._full_window.isVisible(),'fullscreen not visible'
            n.report_viewer._full_window.grab().save(str(out/'04_full_report.png'));n.report_viewer._full_window.close()
            checks.append('evaluation_hides_old_candidates_and_report_readable_fullscreen')
            w.evaluation_path.setText(str(ROOT/'data/damaged/hole.npz'));assert '尚未计算' in r.review_summary.text()
            assert n.viewer.last_comparison is None
            checks.append('new_comparison_selection_invalidates_old_results')
            w.grab().save(str(out/'03_fresh_evaluation.png'));finish()
    except Exception as error:finish(type(error).__name__+': '+str(error))
timer=QTimer();timer.timeout.connect(tick);timer.start(150);sys.exit(app.exec())
