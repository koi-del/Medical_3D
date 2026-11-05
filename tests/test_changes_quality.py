import json
import numpy as np
import pytest
from medical_mesh import MeshAsset,load_mesh,repair_mesh,RepairOptions
from medical_mesh.core.changes import mesh_changes
from medical_mesh.processing.patch_quality import patch_quality
from pathlib import Path


def triangle():
    return MeshAsset(np.array([[0.,0,0],[1,0,0],[.5,np.sqrt(3)/2,0]]),np.array([[0,1,2]]))


def test_reindexing_and_face_order_are_not_changes():
    mesh=triangle();vertices=mesh.vertices[[2,0,1]]
    changed=mesh_changes(mesh,mesh.derive(vertices=vertices,faces=np.array([[1,2,0]])))
    assert not any(changed[k] for k in ('added_face_ids','removed_face_ids','flipped_input_face_ids'))


def test_duplicate_removal_is_one_occurrence_not_all_matching_faces():
    mesh=triangle();before=mesh.derive(faces=np.array([[0,1,2],[0,1,2]]))
    changed=mesh_changes(before,mesh)
    assert changed['removed_face_ids']==[1]
    assert changed['added_face_ids']==[]


def test_flips_are_not_counted_as_additions_and_removals():
    mesh=triangle();after=mesh.derive(faces=np.array([[0,2,1]]))
    changed=mesh_changes(mesh,after)
    assert changed['flipped_input_face_ids']==[0]
    assert changed['flipped_output_face_ids']==[0]
    assert changed['added_face_ids']==changed['removed_face_ids']==[]


def test_vertex_movement_is_a_geometric_replacement_not_a_flip():
    mesh=triangle();v=mesh.vertices.copy();v[0,2]=.1
    changed=mesh_changes(mesh,mesh.derive(vertices=v))
    assert changed['removed_face_ids']==changed['added_face_ids']==[0]
    assert changed['flipped_output_face_ids']==[]


def test_equilateral_quality_has_known_angle_and_aspect():
    result=patch_quality(triangle(),[0])
    assert result['minimum_angle_degrees']==pytest.approx(60)
    assert result['maximum_aspect_ratio']==pytest.approx(2/np.sqrt(3))
    assert result['maximum_seam_angle_degrees'] is None
    assert result['warnings']==[]


def test_skinny_and_collapsed_triangles_have_explicit_indicators():
    mesh=triangle();v=mesh.vertices.copy();v[2]=[.5,.001,0]
    quality=patch_quality(mesh.derive(vertices=v),[0])
    assert quality['minimum_angle_degrees']<1 and quality['maximum_aspect_ratio']>100
    assert quality['warnings']
    collapsed=mesh.derive(faces=np.array([[0,0,1]]))
    quality=patch_quality(collapsed,[0])
    assert quality['degenerate_face_ids']==[0] and quality['maximum_aspect_ratio'] is None
    json.dumps(quality,allow_nan=False)


def test_seams_exclude_internal_patch_edges_and_use_oriented_normals():
    mesh=MeshAsset(np.array([[0.,0,0],[1,0,0],[1,1,0],[0,1,0]]),np.array([[0,1,2],[0,2,3]]))
    assert patch_quality(mesh,[0])['maximum_seam_angle_degrees']==pytest.approx(0)
    assert patch_quality(mesh,[0,1])['seam_edge_count']==0
    faces=mesh.faces.copy();faces[1]=faces[1,[0,2,1]]
    assert patch_quality(mesh.derive(faces=faces),[0])['maximum_seam_angle_degrees']==pytest.approx(180)


def test_repair_records_changes_and_patch_quality_for_review_and_export():
    root=Path(__file__).resolve().parents[1]
    mesh=load_mesh(root/'data/damaged/hole.npz')
    _,result=repair_mesh(mesh,RepairOptions(fill_boundary_ids=(0,)))
    assert result.accepted
    assert len(result.metrics['changes']['added_face_ids'])==1
    assert result.metrics['patch_quality']['face_count']==1
    assert result.metrics['patch_quality']['seam_edge_count']==3
    json.dumps(result.to_dict(),allow_nan=False)
    _,result=repair_mesh(mesh,RepairOptions(orient_faces=True))
    assert result.metrics['patch_quality']['status']=='not_applicable'
