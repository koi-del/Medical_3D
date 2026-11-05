import json
import numpy as np
import pytest
from medical_mesh import detect_defects,repair_mesh,RepairOptions
from medical_mesh.core.review import CandidateReview,comparison_rows
from medical_mesh.core.versions import VersionStore
from medical_mesh.data.synthetic import tetrahedron,open_tube,inject_defects
from medical_mesh.ui.picking import nearest_boundary


def make_review(tmp_path):
    original,_=inject_defects(tetrahedron(),'duplicate')
    candidate,result=repair_mesh(original,RepairOptions(remove_duplicates=True))
    return CandidateReview(original,candidate,result.to_dict(),tmp_path)


def test_review_does_not_commit_until_accepted(tmp_path):
    review=make_review(tmp_path/'job');store=VersionStore(tmp_path/'versions')
    store.commit(review.input_asset)
    assert store.current_version==review.input_asset.version
    assert json.loads((review.output_dir/'review.json').read_text())['decision']=='pending'
    accepted=review.resolve(review.input_asset,True);store.commit(accepted)
    assert store.current_version==review.candidate.version
    assert store.rollback().version==review.input_asset.version
    with pytest.raises(ValueError):review.resolve(review.input_asset,True)


def test_discard_leaves_input_unchanged(tmp_path):
    review=make_review(tmp_path)
    before=review.input_asset.geometry_hash()
    assert review.resolve(review.input_asset,False) is review.input_asset
    assert review.input_asset.geometry_hash()==before
    assert json.loads((tmp_path/'review.json').read_text())['decision']=='discarded'


def test_redo_only_restores_direct_child_and_preserves_geometry(tmp_path):
    review=make_review(tmp_path/'job');store=VersionStore(tmp_path/'versions')
    store.commit(review.input_asset);store.commit(review.candidate)
    expected=review.candidate.geometry_hash();store.rollback()
    with pytest.raises(ValueError):store.redo(review.input_asset.version)
    assert store.current_version==review.input_asset.version
    assert store.redo(review.candidate.version).geometry_hash()==expected
    with pytest.raises(ValueError):store.redo(review.candidate.version)


def test_stale_or_rejected_candidate_cannot_be_accepted(tmp_path):
    review=make_review(tmp_path)
    with pytest.raises(ValueError):review.resolve(review.input_asset.derive(),True)
    assert review.decision=='pending'
    with pytest.raises(ValueError):CandidateReview(review.input_asset,review.candidate,{'status':'rejected'},tmp_path)


def test_metric_comparison_is_bound_to_actual_diagnoses(tmp_path):
    review=make_review(tmp_path)
    rows=comparison_rows(review.result['diagnosis_before'],review.result['diagnosis_after'])
    assert ('重复面',1,0) in rows
    assert ('连通分量',1,1) in rows


def test_boundary_pick_does_not_guess_distant_points():
    asset=open_tube();d=detect_defects(asset).to_dict()
    for boundary in d['boundaries']:
        a,b=boundary['edges'][0]
        p=asset.vertices[[a,b]].mean(axis=0)
        assert nearest_boundary(asset,d,p)==boundary['id']
    assert nearest_boundary(asset,d,[100,100,100]) is None
    assert nearest_boundary(asset,d,[np.nan,0,0]) is None


def test_orientation_repair_minimizes_changed_faces_even_when_seed_is_flipped():
    base=tetrahedron()
    faces=base.faces.copy();faces[0]=faces[0,[0,2,1]]
    damaged=base.derive(faces=faces)
    candidate,result=repair_mesh(damaged,RepairOptions(orient_faces=True))
    assert result.accepted,result.errors
    assert np.array_equal(candidate.faces,base.faces)
    operation=next(x for x in result.operations if x['operation']=='coherent_orientation')
    assert operation['candidate_face_ids']==[0]
