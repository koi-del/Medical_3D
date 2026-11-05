"""Real GUI: manual import, optimize, shared review, accept, rollback and cancellation."""
import json
import os
import sys
import time
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_API','pyside6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from medical_mesh.ui.workbench import Workbench
from medical_mesh.member2.cad import probe_freecad

out=ROOT/'results/member2_merge';out.mkdir(exist_ok=True)
app=QApplication(sys.argv);window=Workbench(ROOT,out/'sessions'/uuid.uuid4().hex)
window.show();panel=window.repair;numeric=window.numerical
stage=0;started=time.monotonic();checks=[];version=None;cancel_sent=False


def finish(error=None):
    timer.stop()
    (out/'gui_verification.json').write_text(json.dumps(dict(status='failed' if error is not None else 'completed',
        checks=checks,error=error,freecad=probe_freecad()),ensure_ascii=False,indent=2),encoding='utf-8')
    print(checks,error,flush=True)
    if panel.process:panel.cancel();panel.process.waitForFinished(3000)
    if numeric.jobs.busy:numeric.jobs.cancel()
    window.close();app.exit(1 if error is not None else 0)


def tick():
    global stage,version,cancel_sent
    try:
        if time.monotonic()-started>120:raise RuntimeError('Unified GUI validation timeout')
        if stage==0:
            assert panel.asset is None and numeric.current_asset is None
            assert set(numeric.pages)=={'optimization','cad'}
            assert len(window.steps)==4
            checks.append('manual_start_without_auto_demo_or_sample_loading')
            panel.self_check.setChecked(True);panel.start_job('load',input_path=str(ROOT/'data/reference/sphere.npz'))
            stage=1;return
        if panel.process is not None or numeric.jobs.busy:return
        if stage==1:
            assert panel.asset is not None,panel.log.toPlainText()
            version=panel.asset.version
            assert numeric.current_asset.version_id==version
            assert numeric.current_asset.geometry_hash==__import__('medical_mesh.integration.member2',fromlist=['to_optimization']).to_optimization(panel.asset).geometry_hash
            checks.append('accepted_reference_identity_coordinates_and_units_synced')
            numeric.operation.setCurrentIndex(numeric.operation.findData('laplacian'));numeric.iterations.setValue(0);numeric.samples.setValue(500)
            window.set_step('optimize');numeric.run_optimization();stage=2;return
        if stage==2:
            result=numeric.optimization_result
            assert result and result['decision']=='accepted',numeric.log.toPlainText()
            assert numeric.current_candidate and panel.asset.version==version
            assert (numeric.optimization_dir/'report.html').exists()
            assert result['attempts'][0]['final_metrics']['samples_each_direction']==50000
            checks.append('qprocess_optimization_real_provider_independent_50k_check_and_report')
            window.grab().save(str(out/'optimization.png'))
            window.review_optimization();assert panel.process is not None,numeric.log.toPlainText();stage=3;return
        if stage==3:
            assert panel.pending_review is not None,panel.log.toPlainText()
            assert panel.asset.version==version and panel.store.current_version==version
            checks.append('shared_review_does_not_commit_candidate_early')
            window.grab().save(str(out/'shared_preview.png'))
            panel.accept_preview();assert panel.asset.version!=version
            assert numeric.current_asset.version_id==panel.asset.version
            checks.append('human_accept_commits_shared_version_and_refreshes_optimization_reference')
            panel.rollback();assert panel.asset.version==version
            assert numeric.current_asset.version_id==version
            checks.append('rollback_restores_both_modules_reference')
            stage=4;return
        if stage==4:
            numeric.run_optimization();stage=5
            QTimer.singleShot(10,numeric.jobs.cancel);return
        if stage==5:
            assert numeric.last_result['status']=='cancelled',numeric.last_result
            assert panel.asset.version==version
            checks.append('windows_task_cancel_keeps_formal_version_and_returns_idle')
            window.set_step('optimize');window.grab().save(str(out/'merged_workbench.png'))
            finish()
    except Exception as error:finish(str(error))


timer=QTimer();timer.timeout.connect(tick);timer.start(150)
sys.exit(app.exec())
