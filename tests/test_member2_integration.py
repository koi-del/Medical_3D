import copy
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pytest
from medical_mesh import load_mesh,save_mesh,detect_defects
from medical_mesh.integration.member2 import to_optimization,from_optimization,diagnose_pair
from medical_mesh.integration.review import validate_optimization
from medical_mesh.member2.core.model import save_asset,load_asset
from medical_mesh.member2.optimization.search import optimize_mesh,Limits,check_diagnosis
from medical_mesh.member2.evaluation import EvaluationConfig
from medical_mesh.member2.jobs.worker import dispatch
from medical_mesh.processing.mesh_worker import run_job

ROOT=Path(__file__).resolve().parents[1]


def sphere():return load_mesh(ROOT/'data/reference/sphere.npz')


def optimize(asset,directory):
    # Nontrivial QEM test; broad test thresholds are explicit and stay out of GUI defaults.
    return optimize_mesh(to_optimization(asset),[{'operation':'qem','keep_ratio':.8}],directory,
        EvaluationConfig(150,42),EvaluationConfig(400,142),Limits(1,1,1),diagnose_pair)


def test_bridge_preserves_coordinates_identity_units_and_npz_formats(tmp_path):
    original=sphere();converted=to_optimization(original)
    restored=from_optimization(converted)
    assert original.metadata()==restored.metadata()
    assert np.array_equal(original.vertices,restored.vertices)
    save_asset(converted,tmp_path/'member2.npz')
    assert load_mesh(tmp_path/'member2.npz').metadata()==original.metadata()
    save_mesh(original,tmp_path/'member1.npz')
    assert load_mesh(tmp_path/'member1.npz').metadata()==original.metadata()


def test_invalid_npz_sidecar_hash_is_rejected(tmp_path):
    path=save_asset(to_optimization(sphere()),tmp_path/'data.npz')
    metadata=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    metadata['geometry_sha256']='wrong';path.with_suffix('.json').write_text(json.dumps(metadata),encoding='utf-8')
    with pytest.raises(ValueError,match='hash'):load_mesh(path)


def test_real_provider_rejects_boundary_motion_even_when_loop_count_matches():
    original=load_mesh(ROOT/'data/reference/open_tube.npz');reference=to_optimization(original)
    candidate=reference.derive(reference.vertices+[.1,0,0],reference.faces,'translation',{})
    result=check_diagnosis(diagnose_pair,reference,candidate)
    assert result['status']=='failed'
    assert result['details']['checks']['boundary_correspondence']=='failed'


def test_invalid_reference_and_unknown_roi_cannot_pass_full_gate():
    bad=to_optimization(load_mesh(ROOT/'data/damaged/non_manifold_edge.npz'))
    assert check_diagnosis(diagnose_pair,bad,bad)['status']=='failed'
    original=to_optimization(sphere());original.metadata['protected_rois']=[{'id':'unmapped_region'}]
    assert check_diagnosis(diagnose_pair,original,original)['status']=='unverified'


def test_optimization_enters_shared_review_without_mutating_input(tmp_path):
    original=sphere();geometry=original.geometry_hash()
    verification=optimize(original,tmp_path/'optimization')
    assert verification['decision']=='accepted'
    attempt=next(a for a in verification['attempts'] if a['candidate_id']==verification['selected_candidate'])
    candidate=from_optimization(load_asset(attempt['mesh_path']),original)
    result=validate_optimization(original,candidate,verification)
    assert result.accepted and result.output_version==candidate.version
    assert candidate.parent_version==original.version and len(candidate.faces)<len(original.faces)
    assert geometry==original.geometry_hash()
    assert result.diagnosis_after['self_intersection']['status']=='verified'
    save_mesh(original,tmp_path/'native.npz');save_mesh(candidate,tmp_path/'candidate.npz')
    worker=run_job(dict(operation='review_optimization',input_path=str(tmp_path/'native.npz'),output_dir=str(tmp_path/'review'),
        parameters=dict(candidate_path=str(tmp_path/'candidate.npz'),verification=verification)))
    assert worker['accepted'] and worker['output_version']==candidate.version
    stale=copy.deepcopy(verification);stale['input_version']='other'
    with pytest.raises(ValueError,match='失配'):validate_optimization(original,candidate,stale)
    with pytest.raises(ValueError,match='几何'):validate_optimization(original,replace(candidate,vertices=candidate.vertices+1),verification)
    unverified=copy.deepcopy(verification);unverified['attempts'][0]['diagnosis']['status']='unverified'
    with pytest.raises(ValueError,match='结构复核'):validate_optimization(original,candidate,unverified)


def test_automatic_demonstration_operation_is_removed(tmp_path):
    result=dispatch(dict(operation='patella_demo',output_dir=str(tmp_path/'unsupported')))
    assert result['status']=='failed' and 'Unsupported' in result['errors'][0]
    assert (tmp_path/'unsupported/report.html').exists()
    root=ROOT/'src/medical_mesh/member2'
    assert not (root/'ui/patella_demo.py').exists()
    assert not (root/'experiments/demo.py').exists()


def test_unified_cli_evaluates_native_files_without_demo(tmp_path):
    from medical_mesh.cli import main
    output=tmp_path/'evaluation'
    assert main(['evaluate','--input',str(ROOT/'data/reference/sphere.npz'),
        '--candidate',str(ROOT/'data/reference/sphere.npz'),'--samples','100','--out',str(output)])==0
    result=json.loads((output/'result.json').read_text(encoding='utf-8'))
    assert result['metrics']['sampled_max']<1e-12
    assert (output/'report.html').exists() and (output/'results.csv').exists()
    with pytest.raises(SystemExit):main(['patella-demo'])


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows-owned process-tree cleanup')
def test_cad_timeout_cleans_owned_windows_descendant(tmp_path):
    import ctypes
    import subprocess
    import sys
    from medical_mesh.member2.cad.runner import run_worker
    pid_file=tmp_path/'child_pid.txt';script=tmp_path/'fake_cad.py'
    script.write_text('import subprocess,sys,time\nfrom pathlib import Path\n'
        'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(15)"],creationflags=subprocess.CREATE_NO_WINDOW)\n'
        f'Path({str(pid_file)!r}).write_text(str(child.pid))\n'
        'time.sleep(15)\n',encoding='utf-8')
    with pytest.raises(subprocess.TimeoutExpired):
        run_worker({'executable':sys.executable,'arguments':[str(script)],'timeout_seconds':.8},
            {'mode':'probe'},tmp_path/'job','nested_timeout')
    assert pid_file.exists()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,int(pid_file.read_text()))
    if handle:
        code=ctypes.c_ulong();assert kernel.GetExitCodeProcess(handle,ctypes.byref(code))
        kernel.CloseHandle(handle);assert code.value!=259
