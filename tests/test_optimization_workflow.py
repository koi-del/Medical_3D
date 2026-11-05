from pathlib import Path
import numpy as np
import pytest
from medical_mesh import load_mesh
from medical_mesh.integration.member2 import to_optimization,diagnose_pair
from medical_mesh.member2.core.model import load_asset
from medical_mesh.member2.optimization.filters import process_mesh
from medical_mesh.member2.optimization.search import optimize_mesh,verify_selected,Limits,check_diagnosis
from medical_mesh.member2.evaluation import EvaluationConfig,evaluate_mesh
from medical_mesh.member2.evaluation.verified_volume import enrich_volume
from medical_mesh.member2.ui.viewer import sampled_face_means

ROOT=Path(__file__).resolve().parents[1]


def test_target_faces_and_quality_qem_keep_reference_immutable():
    reference=to_optimization(load_mesh(ROOT/'data/reference/sphere.npz'));before=reference.geometry_hash
    result=process_mesh(reference,{'operation':'qem','target_faces':240})
    assert len(result.faces)==240 and result.parent_version==reference.version_id
    assert before==reference.geometry_hash
    assert check_diagnosis(diagnose_pair,reference,result)['status']=='passed'
    for bad in (True,3,100000,10.5):
        with pytest.raises(ValueError,match='target_faces'):process_mesh(reference,{'operation':'qem','target_faces':bad})


def test_non_selected_candidate_can_be_finalized_without_regeneration(tmp_path):
    reference=to_optimization(load_mesh(ROOT/'data/reference/sphere.npz'))
    result=optimize_mesh(reference,[{'operation':'qem','keep_ratio':.9},{'operation':'qem','keep_ratio':.8}],tmp_path/'search',
        EvaluationConfig(100,77),EvaluationConfig(200,177),Limits(1,1,1),diagnose_pair)
    chosen=result['attempts'][0]
    assert 'final_metrics' not in chosen and chosen['screening_passed']
    before=load_asset(chosen['mesh_path'])
    final,_=verify_selected(reference,result,chosen['candidate_id'],tmp_path/'selected',diagnose_pair)
    after=load_asset(final['attempts'][0]['mesh_path'])
    assert after.version_id==before.version_id and after.geometry_hash==before.geometry_hash
    assert final['selected_candidate']==chosen['candidate_id'] and final['decision']=='accepted'
    assert final['attempts'][0]['final_metrics']['samples_each_direction']==50000
    assert final['current_version_unchanged'] and final['requires_user_commit']


def test_volume_is_available_only_after_closed_single_shell_verification():
    reference=to_optimization(load_mesh(ROOT/'data/reference/tetrahedron.npz'))
    candidate=reference.derive(reference.vertices*.9,reference.faces,'scaled_test',{})
    metrics,_=evaluate_mesh(reference,candidate,EvaluationConfig(100,3))
    assert metrics['volume_change'] is None
    diagnosis=check_diagnosis(diagnose_pair,reference,candidate);enrich_volume(metrics,reference,candidate,diagnosis)
    assert metrics['volume_status']=='verified_single_closed_shell'
    assert metrics['volume_change']==pytest.approx(1-.9**3)
    unknown,_=evaluate_mesh(reference,candidate,EvaluationConfig(100,3))
    enrich_volume(unknown,reference,candidate,{'status':'unverified'})
    assert unknown['volume_change'] is None
    tube=to_optimization(load_mesh(ROOT/'data/reference/open_tube.npz'));open_metrics,_=evaluate_mesh(tube,tube,EvaluationConfig(100,3))
    enrich_volume(open_metrics,tube,tube,check_diagnosis(diagnose_pair,tube,tube))
    assert open_metrics['volume_change'] is None


def test_surface_error_means_do_not_turn_unsampled_faces_into_zero():
    values=sampled_face_means(3,np.array([0,0,2]),np.array([1.,3.,5.]))
    assert values[0]==2 and np.isnan(values[1]) and values[2]==5
    with pytest.raises(ValueError,match='IDs'):sampled_face_means(3,np.array([4]),np.array([1.]))


def test_selected_candidate_worker_uses_new_job_identity(tmp_path):
    from medical_mesh.member2.core.model import save_asset
    from medical_mesh.member2.jobs.worker import dispatch
    reference=to_optimization(load_mesh(ROOT/'data/reference/sphere.npz'))
    verification=optimize_mesh(reference,[{'operation':'qem','keep_ratio':.9},{'operation':'qem','keep_ratio':.8}],tmp_path/'before',
        EvaluationConfig(100,7),EvaluationConfig(200,10007),Limits(1,1,1),diagnose_pair)
    verification.update(run_id='old_job',output_dir=str(tmp_path/'before'),operation='optimize')
    path=save_asset(reference,tmp_path/'reference.npz')
    result=dispatch(dict(operation='verify_candidate',input_path=str(path),verification=verification,
        candidate_id='candidate_00',output_dir=str(tmp_path/'new_job'),provider='medical_mesh.integration.member2:diagnose_pair'))
    assert result['status']=='completed' and result['run_id']=='new_job'
    assert result['operation']=='verify_candidate' and result['decision']=='accepted'


def test_remesh_quality_refinement_improves_shape_without_changing_budget():
    from medical_mesh.member2.evaluation.metrics import quality
    reference=to_optimization(load_mesh(ROOT/'data/reference/sphere.npz'))
    parameters={'operation':'remesh','target_edge_length':.2,'iterations':3}
    baseline=process_mesh(reference,{**parameters,'quality_refinement':False})
    refined=process_mesh(reference,{**parameters,'quality_refinement':True})
    assert len(refined.faces)==len(baseline.faces)
    assert quality(refined)['q_p5']>=quality(baseline)['q_p5']
    assert refined.parameters['quality_refinement']['requested_passes']==3
    assert check_diagnosis(diagnose_pair,reference,refined)['status']=='passed'
