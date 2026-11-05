"""Click the real one-click workflow, including cancellation, failure and replay."""
from pathlib import Path
import sys,json,traceback,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from medical_mesh.ui.bootstrap import configure_qt
configure_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from medical_mesh.ui.main_window import MainWindow
from medical_mesh.core.model import write_json,file_hash
from medical_mesh.experiments.demo import DIRECTIONS

out=ROOT/'runs/gui_patella_demo_smoke';out.mkdir(parents=True,exist_ok=True)
configure_qt();app=QApplication([]);app.setStyle('Fusion')
w=MainWindow(ROOT);w.load_demo();w.tabs.setCurrentWidget(w.demo);w.workspace.setCurrentWidget(w.demo_overview);w.show()
formal_version,formal_hash=w.current_asset.version_id,w.current_asset.geometry_hash
baseline=ROOT/'runs/medical_patella_verified_20261022'
preserved_report=ROOT.parent/'outputs/真实MRI髌骨模型_课设实验报告/实验报告.md'
preserved_hash=file_hash(preserved_report)
completed=[];errors=[];mode=None;events=[];heartbeats=0;done=False
pulse=QTimer();pulse.setInterval(50)
def tick():
    global heartbeats
    heartbeats+=1
pulse.timeout.connect(tick);pulse.start()

def press(widget,button):
    w.demo.scroll.ensureWidgetVisible(widget)
    QTest.mouseClick(widget,button)

def abort(error):
    global done
    if done:return
    done=True;errors.append(str(error));traceback.print_exc()
    write_json(out/'verification.json',{'status':'failed','errors':errors,'completed':completed})
    w.jobs.cancel();QTimer.singleShot(1200,lambda:app.exit(2))

def start(kind):
    global mode
    mode=kind
    try:
        print('START',kind,flush=True)
        if kind=='failed_source':
            bad=out/'bad_source';bad.mkdir(exist_ok=True);(bad/'knee-2016-09.zip').write_bytes(b'corrupt archive')
            w.demo_source_dir=bad
        else:w.demo_source_dir=ROOT/'data/public/spl_knee/source'
        press(w.demo.run_button,Qt.LeftButton)
        assert w.jobs.busy
        assert not w.demo.run_button.isEnabled() and not w.run_button.isEnabled() and not w.cad.run_button.isEnabled()
        assert w.demo_overview.bar.value()==0 and w.demo_overview.optimization.rowCount()==0
        assert not w.report_button.isEnabled() and not w.demo.compare_button.isEnabled()
        assert all(w.demo_overview.conversions.item(i,3).text()=='未执行' for i in range(6))
        if kind=='cancel':QTimer.singleShot(250,lambda:QTest.mouseClick(w.cancel_button,Qt.LeftButton))
    except Exception as error:abort(error)

def event(value):
    if mode=='full':
        events.append(value)
        if value['stage']=='demo_phase':print('PHASE',value['data'].get('phase'),value['data'].get('status'),flush=True)
w.jobs.event.connect(event)

def received(result):
    try:
        print('FINISHED',mode,result['status'],flush=True)
        assert not w.jobs.busy and w.demo.run_button.isEnabled()
        assert w.current_asset.version_id==formal_version and w.current_asset.geometry_hash==formal_hash
        assert file_hash(preserved_report)==preserved_hash,'demo overwrote previously delivered report'
        completed.append({'case':mode,'status':result['status'],'directory':str(w.demo_dir)})
        if mode in ('cancel','failed_source'):
            assert result['status']==('cancelled' if mode=='cancel' else 'failed'),result
            assert not result.get('all_geometry_checks_passed')
            assert not w.demo_overview.available and not w.viewer.assets
            assert w.demo_overview.bar.value()==0
            assert w.demo_reference is None and w.demo_candidate is None
            assert w.report_button.isEnabled()
            press(w.demo.report_button,Qt.LeftButton)
            assert result['status'] in w.report_viewer.browser.toPlainText()
            QTimer.singleShot(300,lambda:start('failed_source' if mode=='cancel' else 'full'))
            return
        assert result['status']=='completed',result
        assert result['sample_storage']=='presentation'
        assert result['execution_mode']=='recomputed' and result['quality_status']=='unverified'
        assert result['all_geometry_checks_passed'] and w.demo_overview.bar.value()==5
        assert len(w.demo_overview.rows)==10 and len(w.demo_overview.available)==6
        assert w.demo_candidate.metadata['quality_status']=='unverified'
        assert w.demo_candidate.parent_version==w.demo_reference.version_id
        assert '实际重新计算' in w.demo_overview.mode.text()
        assert len([e for e in events if e['stage']=='conversion_done'])==6
        assert any(e['stage']=='stability' for e in events)
        for direction in DIRECTIONS:
            data=json.loads((w.demo_dir/'conversion'/direction/'result.json').read_text())
            assert data['geometry_status']=='passed' and data['metrics']['samples_each_direction']==50000
            assert data['export']['pid']!=data['readback']['pid']!=data['readback_coarse']['pid']
            assert data['output_path'].startswith(str(w.demo_dir))
        assert (w.demo_dir/'optimization/qem_2400/final_samples.npz').exists()
        assert not (w.demo_dir/'optimization/qem_6000/final_samples.npz').exists()
        assert not (w.demo_dir/'conversion/stl_to_step/end_to_end_original_samples.npz').exists()
        w.workspace.setCurrentWidget(w.demo_overview);w.grab().save(str(out/'live_completed_overview.png'))
        press(w.demo.compare_button,Qt.LeftButton)
        assert w.workspace.currentWidget() is w.viewer
        assert len(w.viewer.assets[0].faces)==49862 and len(w.viewer.assets[1].faces)==2400
        w.grab().save(str(out/'original_vs_optimized.png'))
        w.workspace.setCurrentWidget(w.demo_overview);w.demo_overview.conversions.selectRow(4)
        QTest.mouseClick(w.demo_overview.view_conversion,Qt.LeftButton)
        assert w.conversion_results.result['source_format']=='igs' and w.conversion_results.result['target_format']=='stl'
        assert w.workspace.currentWidget() is w.conversion_results
        w.grab().save(str(out/'selected_direction.png'))
        w.workspace.setCurrentWidget(w.demo_overview)
        QTest.mouseClick(w.demo_overview.view_report,Qt.LeftButton)
        assert w.workspace.currentWidget() is w.report_viewer and 'end_to_end_original' in w.report_viewer.raw.toPlainText()
        press(w.demo.report_button,Qt.LeftButton)
        text=w.report_viewer.browser.toPlainText()
        assert '公开MRI' in text and '2,400' in text
        assert '本目录没有另行运行工程回归测试' in text,'historical testing was claimed for a new run'
        w.grab().save(str(out/'in_window_report.png'))
        # A fresh window must reopen both the dashboard and its concrete readback artifacts.
        fresh=MainWindow(ROOT);fresh.load_saved_task(w.demo_dir/'result.json')
        assert fresh.demo_replay and '未重新计算' in fresh.demo_overview.mode.text()
        assert fresh.demo_overview.bar.value()==5 and len(fresh.demo_overview.available)==6
        assert fresh.current_asset is None
        fresh.show_demo_conversion('stl_to_step');assert fresh.viewer.assets[1].unit_name=='mm'
        fresh.close()
        assert heartbeats>200,'event loop stalled'
        write_json(out/'verification.json',{'status':'passed','completed':completed,'events':len(events),'ui_heartbeat_count':heartbeats,
            'six_actual_conversions':True,'independent_readbacks':True,'optimization_configurations':10,'samples_each_direction':50000,
            'cancellation_and_failure_recovery':True,'formal_reference_unchanged':True,'prior_delivered_report_unchanged':True,
            'new_window_history':True,'in_window_report':True,'selected_direction_details':True,'run_directory':str(w.demo_dir)})
        finish()
    except Exception as error:abort(error)

def finish():
    global done
    done=True;w.close();app.quit()

def initial():
    try:
        index=w.demo.history.findData(str(baseline));assert index>=0
        w.demo.history.setCurrentIndex(index);press(w.demo.replay_button,Qt.LeftButton)
        assert '未重新计算' in w.demo_overview.mode.text() and len(w.demo_overview.available)==6
        import medical_mesh.experiments.demo as demo_module
        from types import SimpleNamespace
        original=demo_module.shutil.disk_usage
        try:
            demo_module.shutil.disk_usage=lambda path:SimpleNamespace(free=0)
            press(w.demo.run_button,Qt.LeftButton)
            assert not w.jobs.busy and '空间不足' in w.status_label.text()
        finally:demo_module.shutil.disk_usage=original
        QTimer.singleShot(200,lambda:start('cancel'))
    except Exception as error:abort(error)

w.jobs.finished.connect(received)
QTimer.singleShot(500,initial)
QTimer.singleShot(600000,lambda:abort(RuntimeError('GUI suite timeout')))
code=app.exec()
raise SystemExit(code if done and not errors and len(completed)==3 else 2)
