"""Compare optimized policies against frozen same-input E-3D benchmark results."""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from medical_mesh import load_mesh,save_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.processing.suggestions import suggest_non_manifold_repairs
from audit_complex_benchmark import evaluate


def main():
    base=ROOT/'results/e3d_complex';out=ROOT/'results/specialist_optimization';out.mkdir(exist_ok=True)
    cases=json.loads((base/'cases.json').read_text(encoding='utf-8'));rows=[]
    for case in cases:
        name=case['case'];path=base/'inputs'/(name+'.stl')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==case['input_sha256']
        original=load_mesh(path);current=original;steps=[]
        if case['category']=='hole':
            diagnosis=detect_defects(current)
            inner=min(diagnosis.boundaries,key=lambda b:b['span'])['id']
            roles={str(b['id']):'repair_target' if b['id']==inner else 'natural' for b in diagnosis.boundaries}
            current,result=repair_mesh(current,RepairOptions(fill_boundary_ids=(inner,),boundary_roles=roles,
                hole_method='surface',check_self_intersection=True))
            steps.append(result.to_dict())
        else:
            current,result=repair_mesh(current,RepairOptions(remove_duplicates=True,remove_degenerate=True,
                orient_faces=True,check_self_intersection=True));steps.append(result.to_dict())
            proposals=suggest_non_manifold_repairs(current,max_candidates=48);steps.append(proposals.to_dict())
            if proposals.metrics['suggestions']:
                plan=proposals.metrics['suggestions'][0]
                current,result=repair_mesh(current,RepairOptions(delete_face_ids=plan['delete_face_ids'],
                    split_vertex_ids=plan['split_vertex_ids'],check_self_intersection=True));steps.append(result.to_dict())
            d=detect_defects(current)
            if case.get('expected_loops')==0 and not d.metrics['non_manifold_edge_count'] and not d.metrics['non_manifold_vertex_count']:
                targets=tuple(b['id'] for b in d.boundaries if b['kind']=='simple_loop')
                if targets:
                    current,result=repair_mesh(current,RepairOptions(fill_boundary_ids=targets,check_self_intersection=True))
                    steps.append(result.to_dict())
        save_mesh(current,out/(name+'.npz'));save_mesh(current,out/(name+'.stl'))
        record=dict(case=name,input_sha256=case['input_sha256'],steps=steps,
            native=evaluate(current,case,original),stl=evaluate(load_mesh(out/(name+'.stl')),case,original))
        (out/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        vendor=json.loads((base/(name+'_vendor_audit.json')).read_text(encoding='utf-8'))
        old=json.loads((base/(name+'_project_stl_audit.json')).read_text(encoding='utf-8'))
        def rms(r):return r.get('sampled_distance',{}).get('reference_to_output',{}).get('rms')
        row=dict(case=name,before_pass=old['goal_passed'],optimized_native_pass=record['native']['goal_passed'],
            optimized_stl_pass=record['stl']['goal_passed'],vendor_pass=vendor['goal_passed'],
            optimized_rms=rms(record['stl']),vendor_rms=rms(vendor))
        rows.append(row);print(row,flush=True)
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


if __name__=='__main__':main()
