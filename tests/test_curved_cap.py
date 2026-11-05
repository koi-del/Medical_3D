import numpy as np
from medical_mesh import detect_defects,repair_mesh,RepairOptions
from medical_mesh.data.optimization_cases import quadric_annulus,unequal_components


def options(mesh,method='quadric',check=True):
    boundaries=detect_defects(mesh).boundaries
    inner=min(boundaries,key=lambda b:b['span'])['id']
    roles={str(b['id']):'repair_target' if b['id']==inner else 'natural' for b in boundaries}
    return RepairOptions(fill_boundary_ids=(inner,),boundary_roles=roles,
                         hole_method=method,check_self_intersection=check)


def test_nonplanar_hole_uses_neighborhood_curvature_and_keeps_outer_rim():
    mesh=quadric_annulus()
    candidate,result=repair_mesh(mesh,options(mesh))
    assert result.accepted,result.errors
    assert np.array_equal(candidate.vertices[:len(mesh.vertices)],mesh.vertices)
    assert np.linalg.norm(candidate.vertices[-1]) < 1e-10
    assert detect_defects(candidate).metrics['boundary_loop_count']==1
    assert result.diagnosis_after['self_intersection']['face_ids']==[]
    assert result.operations[-1]['method']=='local_quadric_fan'
    assert result.operations[-1]['fit_max_residual'] < 1e-10


def test_curved_fit_is_invariant_to_rotation_and_translation():
    base=quadric_annulus()
    angle=.7;rotation=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
    offset=np.array([12.,-4.,7.])
    mesh=base.derive(vertices=base.vertices@rotation.T+offset)
    candidate,result=repair_mesh(mesh,options(mesh))
    assert result.accepted,result.errors
    assert np.allclose(candidate.vertices[-1],offset,atol=1e-10)


def test_default_planar_method_rejects_nonplanar_hole():
    mesh=quadric_annulus()
    candidate,result=repair_mesh(mesh,options(mesh,method='planar'))
    assert not result.accepted and candidate is mesh


def test_curved_method_requires_self_intersection_verification():
    mesh=quadric_annulus()
    candidate,result=repair_mesh(mesh,options(mesh,check=False))
    assert not result.accepted and candidate is mesh


def test_unstable_or_noisy_context_is_rejected_without_modifying_input():
    mesh=quadric_annulus();vertices=mesh.vertices.copy();vertices[30,2]+=2
    mesh=mesh.derive(vertices=vertices)
    candidate,result=repair_mesh(mesh,options(mesh))
    assert not result.accepted and candidate is mesh


def test_unequal_components_are_preserved_during_orientation_repair():
    mesh=unequal_components();faces=mesh.faces.copy();faces[0]=faces[0,[0,2,1]]
    mesh=mesh.derive(faces=faces)
    candidate,result=repair_mesh(mesh,RepairOptions(orient_faces=True,check_self_intersection=True))
    assert result.accepted,result.errors
    assert detect_defects(candidate).metrics['component_count']==2
    assert len(candidate.faces)==16
