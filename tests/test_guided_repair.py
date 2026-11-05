import json
from pathlib import Path
import numpy as np
import pytest
from medical_mesh import MeshAsset, load_mesh, detect_defects, repair_mesh, RepairOptions
from medical_mesh.core.boundary_roles import BoundaryRoles
from medical_mesh.processing.suggestions import suggest_non_manifold_repairs
from medical_mesh.processing.mesh_worker import run_job
from medical_mesh.data.synthetic import open_tube

ROOT = Path(__file__).resolve().parents[1]


def test_natural_and_uncertain_loops_cannot_be_filled():
    mesh = open_tube()
    for role in ('natural', 'uncertain'):
        output, result = repair_mesh(mesh, RepairOptions(fill_boundary_ids=(0,),
            boundary_roles={'0': role, '1': 'uncertain'}))
        assert not result.accepted
        assert output is mesh


def test_selected_target_closes_only_one_loop():
    mesh = open_tube()
    output, result = repair_mesh(mesh, RepairOptions(fill_boundary_ids=(0,),
        boundary_roles={'0': 'repair_target', '1': 'natural'}, check_self_intersection=True))
    assert result.accepted, result.errors
    assert detect_defects(output).metrics['boundary_loop_count'] == 1
    assert result.operations[-1]['input_boundary_id'] == 0


def test_explicit_delete_does_not_override_natural_opening():
    mesh = open_tube()
    output, result = repair_mesh(mesh, RepairOptions(delete_face_ids=(0,),
        boundary_roles={'0': 'natural', '1': 'natural'}))
    assert output is mesh and not result.accepted


def test_role_decisions_follow_geometry_not_boundary_number(tmp_path):
    mesh = open_tube()
    diagnosis = detect_defects(mesh).to_dict()
    store = BoundaryRoles(tmp_path/'roles.json')
    store.mark(mesh, [diagnosis['boundaries'][0]], 'natural')
    remapped = json.loads(json.dumps(diagnosis))
    for boundary in remapped['boundaries']:
        boundary['id'] = 1-boundary['id']
    mapping = BoundaryRoles(tmp_path/'roles.json').mapping(mesh.derive(), remapped)
    assert mapping == {'1': 'natural', '0': 'uncertain'}
    assert BoundaryRoles(tmp_path/'roles.json').mapping(open_tube(), diagnosis) == {'0': 'uncertain', '1': 'uncertain'}


def test_stale_or_incomplete_roles_rejected():
    mesh = open_tube()
    for roles in ({'0': 'repair_target'}, {'0': 'repair_target', '1': 'natural', '9': 'natural'}):
        _, result = repair_mesh(mesh, RepairOptions(fill_boundary_ids=(0,), boundary_roles=roles))
        assert not result.accepted


def test_suggestion_finds_appended_face_and_exposes_ambiguous_alternative():
    mesh = load_mesh(ROOT/'data/damaged/non_manifold_edge.npz')
    before = mesh.geometry_hash()
    d = detect_defects(mesh).to_dict()
    roles = {str(b['id']): 'uncertain' for b in d['boundaries']}
    result = suggest_non_manifold_repairs(mesh, roles)
    assert mesh.geometry_hash() == before
    assert result.metrics['suggestions'][0]['delete_face_ids'] == [960]
    assert {tuple(p['delete_face_ids']) for p in result.metrics['suggestions'] if len(p['delete_face_ids'])==1} == {(689,), (960,)}
    assert {p['boundary_loops_after'] for p in result.metrics['suggestions']} == {0,1}
    assert all(p['self_intersection_status'] == 'verified' for p in result.metrics['suggestions'])
    assert result.metrics['examined'] >= 3


def test_ambiguous_single_face_removals_are_all_proposals():
    mesh = MeshAsset(vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,-1,0],[0,0,1.]]),
                     faces=np.array([[0,1,2],[1,0,3],[0,1,4]]))
    result = suggest_non_manifold_repairs(mesh)
    assert len(result.metrics['suggestions']) > 1
    assert result.output_version == mesh.version
    assert not result.metrics['truncated']
    limited = suggest_non_manifold_repairs(mesh, max_candidates=1)
    assert limited.metrics['truncated'] and limited.metrics['examined'] == 1


def test_worker_suggestions_are_not_repair_commits(tmp_path):
    result = run_job(dict(operation='suggest', input_path=str(ROOT/'data/damaged/non_manifold_edge.npz'),
                          output_dir=str(tmp_path), parameters={}))
    assert result['status'] == 'completed'
    assert result['input_version'] == result['output_version']
    assert result['metrics']['suggestions'][0]['delete_face_ids'] == [960]
    assert load_mesh(result['output_paths']['mesh']).geometry_hash() == load_mesh(ROOT/'data/damaged/non_manifold_edge.npz').geometry_hash()
