"""Background orchestration for the one-click real MRI demonstration."""
from pathlib import Path
import json
import shutil
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from medical_mesh.core.model import write_json, file_hash

PHASES = [('prepare','来源与原始模型'),('optimize','优化对照与三种子复核'),
          ('convert','六向转换与独立回读'),('controls','负对照'),('report','图文报告与产物审计')]
DIRECTIONS = ['stl_to_step','stl_to_igs','step_to_stl','step_to_igs','igs_to_stl','igs_to_step']


def required_free_bytes(keep_all_samples=False):
    return (512 if keep_all_samples else 160)*1024**2


def check_capacity(destination,source,keep_all_samples=False):
    def ancestor(path):
        path=Path(path).resolve()
        while not path.exists():path=path.parent
        if not path.is_dir():raise ValueError('任务保存位置必须是文件夹')
        return path
    target=ancestor(destination);cache=ancestor(source)
    required=required_free_bytes(keep_all_samples)
    if not (Path(source)/'knee-2016-09.zip').exists():
        if os.stat(target).st_dev==os.stat(cache).st_dev:required+=100*1024**2
        elif shutil.disk_usage(cache).free<100*1024**2:
            raise RuntimeError('源数据缓存所在磁盘空间不足，首次下载需要至少100MiB空余')
    if shutil.disk_usage(target).free<required:
        raise RuntimeError(f'空间不足，当前模式至少需{required/1024**2:.0f}MiB空余；请在“保存位置”选择其他目录')


def finalize_demo(result, directory):
    """Persist terminal state, including failures before a full report was created."""
    directory=Path(directory)
    state_path=directory/'demo_state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    state.update(result)
    if state.get('status') != 'completed':
        for phase in state.get('phases',{}).values():
            if phase['status']=='running':phase['status']=state['status']
        state['all_geometry_checks_passed']=False
    write_json(directory/'demo_result.json',state)
    write_json(state_path,state)
    return state


def run_demo(request,progress):
    from . import patella
    from .patella_report import generate_report
    from medical_mesh.cad.runner import effective_config, probe_freecad
    from medical_mesh.jobs.worker import environment_report
    out=Path(request['output_dir']).resolve()
    root=Path(request['project_dir']).resolve()
    source=Path(request.get('source_dir',root/'data/public/spl_knee/source')).resolve()
    if (out/'provenance.json').exists() or (out/'demo_result.json').exists():
        raise ValueError('演示必须使用新任务目录，不能覆盖已有实验')
    state={'operation':'patella_demo','run_id':out.name,'output_dir':str(out),'status':'running',
           'execution_mode':'recomputed','decision':'needs_review','quality_status':'unverified',
           'formal_version_unchanged':True,'output_version':None,
           'phases':{key:{'title':title,'status':'pending'} for key,title in PHASES},
           'reference_path':str(out/'reference.npz'),'candidate_path':str(out/'selected_candidate.npz'),
           'report_path':str(out/'report.html')}
    def emit(stage,message,data=None):
        progress(stage,message,data or {})
    def phase(key,status,extra=None):
        state['phases'][key]['status']=status
        if extra:state.update(extra)
        write_json(out/'demo_state.json',state)
        emit('demo_phase',dict(PHASES)[key]+'：'+status,{'phase':key,'status':status,'state':state.copy()})
    phase('prepare','running')
    keep_all=bool(request.get('keep_all_samples',False))
    check_capacity(out,source,keep_all)
    write_json(out/'storage_policy.json',{'mode':'complete' if keep_all else 'presentation',
        'all_metrics_samples_each_direction':50000,
        'retained':'all sample arrays' if keep_all else 'selected optimization full samples and six conversion roundtrip full samples',
        'not_retained':[] if keep_all else ['unselected optimization samples','additional seed sample arrays','end-to-end sample arrays'],
        'note':'Metrics, seeds, geometry snapshots and JSON logs are retained for every calculation; point count and thresholds are unchanged.'})
    state['sample_storage']='complete' if keep_all else 'presentation'
    if probe_freecad()['status']!='configured':
        raise RuntimeError('FreeCAD不可用，请先配置运行器')
    config=effective_config({'samples':50000,'seed':patella.SEED+30000,'write_error_figure':True})
    write_json(out/'frozen_cad_config.json',config)
    write_json(out/'environment.json',environment_report())
    write_json(out/'experiment.json',{'date':datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat(),
        'source_case_date':'2026-10-22','structure':'patella','execution_mode':'recomputed',
        'source_url':patella.SOURCE_URL,'script_sha256':file_hash(patella.__file__),
        'started_local':datetime.now(ZoneInfo('Asia/Taipei')).isoformat()})
    reference=patella.prepare(out,source)
    phase('prepare','completed',{'reference_hash':reference.geometry_hash,'reference_version':reference.version_id})
    phase('optimize','running')
    optimization=patella.run_optimization(out,emit,keep_all_samples=keep_all)
    phase('optimize','completed',{'selected':optimization['selected']})
    phase('convert','running')
    conversions=patella.run_conversions(out,emit,run_controls=False,keep_all_samples=keep_all)
    phase('convert','completed' if conversions['passed']==6 else 'failed',{'conversions_passed':conversions['passed']})
    if conversions['passed']!=6:
        raise RuntimeError(f'六向回读仅{conversions["passed"]}/6通过；保留失败记录，不生成成功结论')
    phase('controls','running')
    patella.robustness(out)
    phase('controls','completed')
    phase('report','running')
    generate_report(out,root,publish=False)
    audit=patella.read(out/'artifact_verification.json')
    if not audit['all_passed']:
        raise RuntimeError('最终产物审计未全部通过，请查看artifact_verification.json')
    phase('report','completed',{'all_geometry_checks_passed':True})
    state.update(status='completed',decision='needs_review',quality_status='unverified')
    return finalize_demo(state,out)
