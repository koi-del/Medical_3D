import json
from pathlib import Path
import pytest
from medical_mesh.core.model import write_json


def test_changed_source_archive_rejected_before_extract_or_network(tmp_path):
    from medical_mesh.experiments.patella import prepare
    source=tmp_path/'cache';source.mkdir()
    (source/'knee-2016-09.zip').write_bytes(b'changed upstream or corrupt cache')
    with pytest.raises(ValueError,match='ZIP校验失败'):
        prepare(tmp_path/'experiment',source)
    assert not (source/'Data/Model_98_patella.vtk').exists()


def test_cancelled_demo_preserves_evidence_and_stops_running_phase(tmp_path):
    from medical_mesh.experiments.demo import finalize_demo
    write_json(tmp_path/'demo_state.json',{'phases':{'prepare':{'status':'completed'},
        'optimize':{'status':'running'},'convert':{'status':'pending'}},'reference_hash':'frozen-hash',
        'all_geometry_checks_passed':True})
    result=finalize_demo({'status':'cancelled','decision':'rejected'},tmp_path)
    assert result['phases']['prepare']['status']=='completed'
    assert result['phases']['optimize']['status']=='cancelled'
    assert result['phases']['convert']['status']=='pending'
    assert result['reference_hash']=='frozen-hash'
    assert not result['all_geometry_checks_passed']
    assert json.loads((tmp_path/'demo_result.json').read_text())==result


def test_completed_demo_rich_report_survives_qprocess_collection(tmp_path):
    from PySide6.QtCore import QCoreApplication
    from medical_mesh.jobs.qt_manager import JobManager
    app=QCoreApplication.instance() or QCoreApplication([])
    manager=JobManager()
    class FinishedProcess:
        def readAllStandardOutput(self):return b''
        def readAllStandardError(self):return b''
        def deleteLater(self):pass
    manager.process=FinishedProcess()
    manager.request={'operation':'patella_demo','output_dir':str(tmp_path)}
    rich='<html><h1>Detailed experiment</h1><img src="figures/data.png"></html>'
    (tmp_path/'report.html').write_text(rich)
    write_json(tmp_path/'result.json',{'run_id':tmp_path.name,'operation':'patella_demo',
        'status':'completed','decision':'needs_review','quality_status':'unverified'})
    results=[];manager.finished.connect(results.append)
    manager._finished(0,None)
    assert not manager.busy and results[0]['status']=='completed'
    assert (tmp_path/'report.html').read_text()==rich
    assert json.loads((tmp_path/'result.json').read_text())['quality_status']=='unverified'


def test_utf8_progress_survives_split_qprocess_chunks(tmp_path):
    from PySide6.QtCore import QCoreApplication
    from medical_mesh.jobs.qt_manager import JobManager
    app=QCoreApplication.instance() or QCoreApplication([])
    manager=JobManager();manager.request={'output_dir':str(tmp_path)}
    payload=(json.dumps({'event':'progress','stage':'demo_phase','message':'髌骨优化完成','data':{}},ensure_ascii=False)+'\n').encode()
    split=payload.index('髌'.encode())+1
    class ChunkedProcess:
        chunks=iter([payload[:split],payload[split:]])
        def readAllStandardOutput(self):return next(self.chunks)
    manager.process=ChunkedProcess();events=[];manager.event.connect(events.append)
    manager._read();manager._read()
    assert events[0]['message']=='髌骨优化完成'
    assert (tmp_path/'stdout.log').read_text()==payload.decode()
    manager.process=None


def test_disk_full_log_failure_still_finishes_and_releases_job(tmp_path,monkeypatch):
    import errno
    from PySide6.QtCore import QCoreApplication
    from medical_mesh.jobs.qt_manager import JobManager
    app=QCoreApplication.instance() or QCoreApplication([])
    manager=JobManager();manager.request={'operation':'probe','output_dir':str(tmp_path)}
    class FinishedProcess:
        def readAllStandardOutput(self):return b''
        def readAllStandardError(self):return b''
        def deleteLater(self):pass
    manager.process=FinishedProcess();reasons=[];manager.cancel=lambda reason:reasons.append(reason)
    write_json(tmp_path/'result.json',{'run_id':tmp_path.name,'operation':'probe','status':'completed'})
    original=Path.open
    def open_file(path,*args,**kwargs):
        if path.name=='stdout.log':raise OSError(errno.ENOSPC,'No space left on device')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',open_file)
    manager._log_chunk(tmp_path/'stdout.log','one line')
    results=[];manager.finished.connect(results.append);manager._finished(0,None)
    assert reasons==['failed']
    assert not manager.busy and results[0]['status']=='failed'
    assert results[0]['quality_status']=='unverified'
    assert 'No space' in results[0]['errors'][0]
