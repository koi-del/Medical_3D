import json
import zipfile
import numpy as np
import pytest
from pathlib import Path
from medical_mesh import MeshAsset,load_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.core.project_bundle import save_project,load_project,export_summary
from medical_mesh.core.versions import VersionStore
from medical_mesh.data.synthetic import open_tube,sphere
from medical_mesh.processing.suggestions import suggest_non_manifold_repairs
from medical_mesh.processing.mesh_worker import run_job

ROOT=Path(__file__).resolve().parents[1]


def test_split_vertex_separates_disconnected_fans_without_moving_geometry():
    mesh=load_mesh(ROOT/'data/reference/bowtie_vertex.npz')
    candidate,result=repair_mesh(mesh,RepairOptions(split_vertex_ids=(0,),check_self_intersection=True))
    assert result.accepted,result.errors
    assert detect_defects(candidate).metrics['non_manifold_vertex_count']==0
    assert np.array_equal(candidate.vertices[:len(mesh.vertices)],mesh.vertices)
    assert np.array_equal(candidate.vertices[candidate.faces],mesh.vertices[mesh.faces])
    assert result.metrics['changes']['added_face_ids']==[]
    assert any('STL' in warning for warning in result.warnings)


def test_suggestions_include_validated_vertex_split():
    mesh=load_mesh(ROOT/'data/reference/bowtie_vertex.npz')
    suggestions=suggest_non_manifold_repairs(mesh).metrics['suggestions']
    assert any(p['split_vertex_ids']==[0] and not p['delete_face_ids'] for p in suggestions)


def test_local_pair_search_exposes_changes_and_respects_budget():
    mesh=load_mesh(ROOT/'data/damaged/non_manifold_edge.npz')
    result=suggest_non_manifold_repairs(mesh)
    pairs=[p for p in result.metrics['suggestions'] if len(p['delete_face_ids'])==2]
    assert pairs and all(p['self_intersection_status']=='verified' for p in pairs)
    limited=suggest_non_manifold_repairs(mesh,max_candidates=1)
    assert limited.metrics['examined']==1 and limited.metrics['truncated']
    with pytest.raises(ValueError):suggest_non_manifold_repairs(mesh,max_candidates=1000)


def test_pair_removal_solves_case_where_every_single_removal_fails():
    mesh=MeshAsset(np.array([[0.,0,0],[1,0,0],[.5,1,0],[.5,0,1],[.5,-1,0],[.5,0,-1]]),
                   np.array([[0,1,2],[1,0,3],[0,1,4],[1,0,5]]))
    result=suggest_non_manifold_repairs(mesh)
    assert result.metrics['suggestions']
    assert all(len(plan['delete_face_ids'])==2 for plan in result.metrics['suggestions'])


def make_bundle(tmp_path):
    mesh=open_tube();before=detect_defects(mesh).to_dict()
    candidate,result=repair_mesh(mesh,RepairOptions(fill_boundary_ids=(0,),check_self_intersection=True))
    store=VersionStore(tmp_path/'versions');store.commit(mesh,before);store.commit(candidate,result)
    diagnosis=result.diagnosis_after
    roles={str(b['id']):'natural' for b in diagnosis['boundaries']}
    path=tmp_path/'roundtrip.m3d';save_project(path,candidate,diagnosis,roles,store)
    return path,mesh,candidate,roles


def test_project_roundtrip_preserves_units_roles_geometry_and_history(tmp_path):
    path,original,candidate,roles=make_bundle(tmp_path)
    asset,diagnosis,imported,history=load_project(path)
    assert asset.metadata()==candidate.metadata() and asset.geometry_hash()==candidate.geometry_hash()
    assert diagnosis['input_version']==candidate.version and imported==roles
    assert original.version+'.npz' in history and candidate.version+'.npz' in history


def test_project_worker_import_rechecks_and_reports_real_phases(tmp_path):
    path,_,candidate,roles=make_bundle(tmp_path)
    job=tmp_path/'job'
    result=run_job(dict(operation='load',input_path=str(path),output_dir=str(job),parameters={}))
    assert result['status']=='completed',result['errors']
    assert result['metrics']['imported_boundary_roles']==roles
    assert load_mesh(result['output_paths']['mesh']).geometry_hash()==candidate.geometry_hash()
    assert json.loads((job/'progress.json').read_text(encoding='utf-8'))['status']=='completed'
    assert (job/'imported_history').is_dir()


def test_project_tamper_and_unexpected_paths_are_rejected(tmp_path):
    path,*_=make_bundle(tmp_path)
    with zipfile.ZipFile(path) as source:payload={name:source.read(name) for name in source.namelist()}
    for extra in ('diagnosis.json','../outside.txt'):
        broken=tmp_path/('tampered.m3d' if extra=='diagnosis.json' else 'unsafe.m3d')
        modified={**payload,extra:b'{}'}
        with zipfile.ZipFile(broken,'w') as archive:
            for name,data in modified.items():archive.writestr(name,data)
        with pytest.raises(ValueError):load_project(broken)
    assert not (tmp_path.parent/'outside.txt').exists()


def test_unknown_units_are_not_silently_converted_to_mm():
    mesh=MeshAsset(np.array([[0.,0,0],[1,0,0],[0,2,0]]),np.array([[0,1,2]]))
    assert export_summary(mesh)['dimensions_mm'] is None
    known=MeshAsset(mesh.vertices,mesh.faces,source_unit='cm',unit_to_mm=10,unit_status='confirmed')
    assert export_summary(known)['dimensions_mm']==[10.,20.,0.]
    assert np.array_equal(known.vertices,mesh.vertices)
    invalid=MeshAsset(mesh.vertices,mesh.faces,source_unit='cm',unit_to_mm=-10,unit_status='confirmed')
    assert export_summary(invalid)['dimensions_mm'] is None


def test_display_clustering_never_mutates_exact_geometry():
    import pyvista as pv
    from medical_mesh.ui.display_mesh import display_mesh
    mesh=sphere(64,32)
    data=pv.PolyData(mesh.vertices.copy(),np.column_stack((np.full(len(mesh.faces),3),mesh.faces)).ravel())
    points=data.points.copy();faces=data.faces.copy()
    simplified=display_mesh(data,threshold=10)
    assert 0<simplified.n_cells<=data.n_cells
    assert np.array_equal(data.points,points) and np.array_equal(data.faces,faces)
    assert display_mesh(data,enabled=False) is data
