"""Real user flow: face targets, alternate candidates, color maps, evaluation, review."""
import json,os,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.environ.setdefault('QT_API','pyside6')
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog
from medical_mesh.ui.workbench import Workbench

out=ROOT/'results/workflow_ui_verification';out.mkdir(exist_ok=True)
app=QApplication(sys.argv);window=Workbench(ROOT,out/'sessions'/uuid.uuid4().hex);window.show()
window.root=out;window.numerical.root=out
r=window.repair;n=window.numerical;stage=0;started=time.monotonic();checks=[];original=None;selected=None


def finish(error=None):
    failed=error is not None
    timer.stop();(out/'verification.json').write_text(json.dumps(dict(status='failed' if failed else 'completed',checks=checks,error=error),ensure_ascii=False,indent=2),encoding='utf-8')
    print(checks,error,flush=True);window.close();app.exit(1 if failed else 0)


def tick():
    global stage,original,selected
    try:
        if time.monotonic()-started>150:raise RuntimeError('Workflow validation timeout')
        if r.process is not None or n.jobs.busy:return
        if stage==0:
            for side in (window.left_sidebar,window.right_sidebar):
                QTest.mouseClick(side.edge,Qt.LeftButton);app.processEvents()
                assert side.collapsed and not side.body.isVisible() and side.width()==17
                QTest.mouseClick(side.edge,Qt.LeftButton);app.processEvents()
                assert not side.collapsed and side.body.isVisible()
                QTest.mouseClick(side.close_button,Qt.LeftButton);app.processEvents()
                assert side.closed and not side.isVisible()
                action=next(action for action in window.sidebar_actions.values() if not action.isChecked())
                action.trigger();app.processEvents()
                assert not side.closed and side.isVisible() and side.body.isVisible()
            checks.append('both_sidebars_collapse_expand_close_and_restore_via_menu')
            assert window.left_sidebar.isAncestorOf(window.settings)
            assert window.right_sidebar.isAncestorOf(window.objects)
            assert not window.right_sidebar.isAncestorOf(window.inspector)
            assert not window.results_panel.isVisible()
            window.results_toggle.click();assert window.results_panel.isVisible()
            window.results_toggle.click();assert not window.results_panel.isVisible()
            checks.append('left_parameters_right_objects_and_independently_collapsible_bottom_results')
            assert tuple(window.steps)==('repair','optimize','evaluate','export')
            assert not r.isVisible() and not n.isVisible()
            assert r.import_button.isVisible() and r.export_button.isVisible()
            checks.append('single_workflow_fixed_canvas_global_open_export_and_review')
            r.start_job('load',input_path=str(ROOT/'data/reference/sphere.npz'));stage=1;return
        if stage==1:
            assert r.asset is not None;original=r.asset.version
            window.refresh_state();objects=window.objects;actor=window.viewer.plotter.actors['base_mesh'];before_hash=r.asset.geometry_hash()
            assert objects.tree.topLevelItemCount()==1
            item=objects.tree.topLevelItem(0);item.setCheckState(0,Qt.Unchecked);assert not actor.GetVisibility()
            item.setCheckState(0,Qt.Checked);assert actor.GetVisibility()
            objects.opacity.setValue(42);assert abs(actor.prop.opacity-.42)<1e-6
            objects.set_color('#3366cc');assert abs(actor.prop.color.float_rgb[2]-.8)<1e-5
            objects.name.setText('测试模型显示名');objects._rename();assert item.text(0)=='测试模型显示名'
            assert '包围盒' in objects.info.text() and '表面积' in objects.info.text()
            assert r.asset.geometry_hash()==before_hash and r.asset.version==original
            objects.opacity.setValue(100);objects.set_color('#76bcb2')
            checks.append('version_bound_visibility_color_opacity_alias_properties_do_not_modify_geometry')
            window.grab().save(str(out/'01_check_repair.png'))
            window.set_step('optimize');n.target_mode.setCurrentIndex(1);n.target_faces.setValue(480);n.samples.setValue(300)
            n.limit_d95.setValue(.1);n.limit_max.setValue(.1);n.limit_area.setValue(.5)
            n.run_optimization();stage=2;return
        if stage==2:
            assert n.current_candidate is not None,n.log.toPlainText()
            assert len(n.current_candidate.faces)==480 and r.asset.version==original
            assert n.viewer.error_mode=='surface'
            assert window.results_panel.isVisible() and window.inspector.width()>600
            assert not n.table.isColumnHidden(3)
            window.refresh_state();assert window.objects.tree.topLevelItemCount()==2
            right_actor=n.viewer.plotter.renderers[1].actors['candidate_mesh'];mapper=right_actor.mapper
            window.objects.tree.setCurrentItem(window.objects.tree.topLevelItem(1));window.objects.set_color('#ff2200')
            assert right_actor.mapper is mapper and mapper.scalar_visibility,'object colors must not override the error scalar map'
            assert '接受' in window.feedback.text()
            checks.append('result_object_and_feedback_preserve_error_colormap_and_reference')
            assert 'volume_change' in n.optimization_result['attempts'][0]['final_metrics']
            window.grab().save(str(out/'02_target_faces_and_error_map.png'))
            checks.append('real_target_face_count_50k_verification_and_surface_error_colors')
            n.search.setChecked(True);n.run_optimization();stage=3;return
        if stage==3:
            assert n.optimization_result['selected_candidate']
            first=n.optimization_result['attempts'][0];assert first.get('screening_passed') and 'final_metrics' not in first
            n.table.selectRow(0);n.select_candidate(0,0);selected=n.current_candidate.version_id
            window.review_optimization();assert n.jobs.busy and window._review_requested
            stage=4;return
        if stage==4:
            # The final-check finished signal queues the shared-review worker.
            if not r.pending_review:return
            assert r.asset.version==original and r.pending_review.candidate.version==selected
            assert r.accept_button.isVisible() and r.discard_button.isVisible()
            assert not r.export_button.isEnabled()
            window.refresh_state();app.processEvents()
            assert r.dual_view.isVisible() and r.show_changes.isVisible()
            assert window.viewer.comparing and min(window.viewer.interactor.sizes())>0
            assert window.objects.tree.topLevelItem(1).text(1)=='待接受'
            window.grab().save(str(out/'03_shared_preview.png'))
            checks.append('alternate_candidate_finalized_without_regeneration_then_shared_preview')
            r.discard_preview();assert r.asset.version==original
            window.review_optimization();stage=5;return
        if stage==5:
            assert r.pending_review is not None,r.log.toPlainText()
            r.accept_preview();assert r.asset.version==selected and n.current_asset.version_id==selected
            checks.append('global_discard_and_accept_preserve_version_contract')
            window.set_step('evaluate');window.evaluation_path.setText(str(ROOT/'data/reference/sphere.npz'))
            window.evaluation_samples.setValue(1000);window.evaluate_external();stage=6;return
        if stage==6:
            assert n.last_result['operation']=='evaluate' and n.last_result['status']=='completed',n.log.toPlainText()
            assert r.asset.version==selected
            window.grab().save(str(out/'04_independent_evaluation.png'))
            checks.append('independent_comparison_evaluates_without_replacing_model')
            window.set_step('export');assert n.cad.isVisible() and r.export_info.isVisible(),'Export settings must be visible'
            assert window.viewport.currentIndex()==0,'Native export should show the accepted model'
            window.fit_view()
            window.grab().save(str(out/'05_export.png'))
            checks.append('native_project_mesh_and_cad_export_in_one_workflow')
            original_dialog=QFileDialog.getSaveFileName
            QFileDialog.getSaveFileName=staticmethod(lambda *a,**k:(str(out/'accepted_feedback.npz'),''))
            try:r.export()
            finally:QFileDialog.getSaveFileName=original_dialog
            assert '已导出当前正式版本' in window.feedback.text() and window.folder_button.isEnabled()
            checks.append('native_export_success_feedback_and_result_directory')
            r.rollback();stage=7;return
        if stage==7:
            assert r.asset.version!=selected and r.redo_stack
            window.refresh_state();assert window.redo_button.isEnabled()
            window.redo_button.click();stage=8;return
        if stage==8:
            assert r.asset.version==selected and not r.redo_stack and r.store.current_version==selected
            checks.append('rollback_redo_restores_exact_accepted_version_and_rediagnoses')
            finish()
    except Exception as error:finish(type(error).__name__+': '+str(error))


timer=QTimer();timer.timeout.connect(tick);timer.start(150);sys.exit(app.exec())
