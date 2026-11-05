"""100k/500k performance and same-atlas medical mixed-defect checks."""
import argparse
import gc
import json
import sys
import time
from pathlib import Path
import numpy as np
import pyvista as pv

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from medical_mesh import load_mesh,save_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.data.synthetic import sphere
from medical_mesh.ui.display_mesh import display_mesh

out=ROOT/'results/extended_validation';out.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--large',action='store_true');args=parser.parse_args()
results=[]
for name in ('FMA7197','FMA24474','FMA7204'):
    source=ROOT/'data/medical'/(name+'.stl');mesh=load_mesh(source)
    faces=mesh.faces[1:].copy();faces[100]=faces[100,[0,2,1]]
    faces=np.vstack((faces,faces[20],faces[30,[0,0,1]]))
    damaged=mesh.derive(faces=faces)
    diagnosis=detect_defects(damaged)
    assert len(diagnosis.boundaries)==1
    candidate,result=repair_mesh(damaged,RepairOptions(remove_duplicates=True,remove_degenerate=True,orient_faces=True,
        fill_boundary_ids=(0,),max_hole_span=diagnosis.metrics['bbox_diagonal'],check_self_intersection=True))
    assert result.accepted,(name,result.errors)
    assert result.diagnosis_after['metrics']['topology_passed'] and result.diagnosis_after['self_intersection']['face_ids']==[]
    assert np.array_equal(candidate.vertices,mesh.vertices)
    from medical_mesh.core.changes import mesh_changes
    change=mesh_changes(mesh,candidate)
    assert not any(change[key] for key in ('added_face_ids','removed_face_ids','flipped_output_face_ids'))
    save_mesh(damaged,out/(name+'_mixed_input.npz'));save_mesh(candidate,out/(name+'_mixed_output.npz'))
    (out/(name+'_mixed.json')).write_text(json.dumps(result.to_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
    results.append(dict(case=name+'_mixed',source=str(source.relative_to(ROOT)),same_atlas=True,
        input_faces=len(damaged.faces),output_faces=len(candidate.faces),passed=True,elapsed_seconds=result.elapsed_seconds))
    print(name,'mixed defects verified',flush=True)
if args.large:
    for name,segments,rings in [('100k',256,200),('500k',512,490)]:
        print('Generating',name,flush=True);mesh=sphere(segments,rings)
        before=mesh.geometry_hash();start=time.perf_counter()
        diagnosis=detect_defects(mesh,check_self_intersection=False)
        seconds=time.perf_counter()-start
        assert diagnosis.metrics['topology_passed'] and diagnosis.metrics['boundary_loop_count']==0
        del diagnosis;gc.collect()
        data=pv.PolyData(mesh.vertices.copy(),np.column_stack((np.full(len(mesh.faces),3),mesh.faces)).ravel())
        start=time.perf_counter();simplified=display_mesh(data);display_seconds=time.perf_counter()-start
        assert 0<simplified.n_cells<len(mesh.faces) and mesh.geometry_hash()==before
        if name=='100k':save_mesh(mesh,out/'large_100k_input.npz')
        results.append(dict(case=name,input_faces=len(mesh.faces),input_vertices=len(mesh.vertices),
            displayed_faces=simplified.n_cells,diagnosis_seconds=seconds,display_preparation_seconds=display_seconds,
            self_intersection_status='unverified',geometry_hash=before,passed=True))
        print(name,'diagnosed in',round(seconds,2),'s; display faces',simplified.n_cells,flush=True)
        del mesh,data,simplified;gc.collect()
(out/'summary.json').write_text(json.dumps(dict(status='completed',checks=results,
    scope='Three organs from one BodyParts3D atlas; not independent patients. Large synthetic timing excludes self-intersection and UI render FPS. No E-3D timing comparison.'),
    ensure_ascii=False,indent=2),encoding='utf-8')
print('All expanded checks passed',flush=True)
