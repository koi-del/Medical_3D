"""Expanded analytic/structural checks, separate from the completed E-3D benchmark."""
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from medical_mesh import detect_defects,repair_mesh,RepairOptions,save_mesh
from medical_mesh.data.optimization_cases import quadric_annulus,unequal_components
from medical_mesh.data.synthetic import sphere

out=ROOT/'results/optimization_checks';out.mkdir(exist_ok=True)
rows=[]


def execute(name,mesh,options,expect_accept,expected_loops=None,expected_components=None):
    save_mesh(mesh,out/(name+'_input.npz'))
    candidate,result=repair_mesh(mesh,options)
    assert result.accepted==expect_accept,(name,result.errors)
    if expect_accept:
        d=detect_defects(candidate,check_self_intersection=True)
        assert d.metrics['topology_passed'] and d.self_intersection['face_ids']==[]
        if expected_loops is not None:assert d.metrics['boundary_loop_count']==expected_loops
        if expected_components is not None:assert d.metrics['component_count']==expected_components
    else:assert candidate is mesh
    save_mesh(candidate,out/(name+'_output.npz'))
    (out/(name+'.json')).write_text(json.dumps(result.to_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
    rows.append(dict(case=name,expected_acceptance=expect_accept,actual_acceptance=result.accepted,
                     input_faces=len(mesh.faces),output_faces=len(candidate.faces),
                     elapsed_seconds=result.elapsed_seconds,check_passed=True))
    return candidate


mesh=quadric_annulus();d=detect_defects(mesh)
inner=min(d.boundaries,key=lambda b:b['span'])['id']
roles={str(b['id']):'repair_target' if b['id']==inner else 'natural' for b in d.boundaries}
candidate=execute('quadric_nonplanar_hole',mesh,RepairOptions(fill_boundary_ids=(inner,),
    boundary_roles=roles,hole_method='quadric',check_self_intersection=True),True,1,1)
assert np.linalg.norm(candidate.vertices[-1])<1e-10
execute('nonplanar_default_rejected',mesh,RepairOptions(fill_boundary_ids=(inner,),
    boundary_roles=roles,check_self_intersection=True),False)
execute('natural_opening_fill_rejected',mesh,RepairOptions(fill_boundary_ids=(inner,),
    boundary_roles={str(b['id']):'natural' for b in d.boundaries},check_self_intersection=True),False)
v=mesh.vertices.copy();v[30,2]+=2
execute('noisy_context_rejected',mesh.derive(vertices=v),RepairOptions(fill_boundary_ids=(inner,),
    boundary_roles=roles,hole_method='quadric',check_self_intersection=True),False)
mesh=unequal_components();faces=mesh.faces.copy();faces[0]=faces[0,[0,2,1]]
execute('unequal_components_orientation',mesh.derive(faces=faces),
        RepairOptions(orient_faces=True,check_self_intersection=True),True,0,2)
mesh=sphere(128,64);faces=mesh.faces.copy();faces[17]=faces[17,[0,2,1]]
faces=np.vstack((faces,faces[900],faces[500,[0,0,1]]))
execute('mixed_defects_16130_faces',mesh.derive(faces=faces),RepairOptions(
    remove_duplicates=True,remove_degenerate=True,orient_faces=True,check_self_intersection=True),True,0,1)
(out/'summary.json').write_text(json.dumps(dict(status='completed',checks=rows,
    scope='Synthetic analytic and structural checks only; no new E-3D runs or clinical validation.'),
    ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False,indent=2))
