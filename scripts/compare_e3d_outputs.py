"""Audit exported E-3D outputs without pretending missing runs are failures."""
import sys,csv,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from medical_mesh import load_mesh,detect_defects
from prepare_e3d_benchmark import CASES


def main():
    out=ROOT/'results/e3d_benchmark';rows=[]
    for name,source,reference,task,loops,components in CASES:
        path=out/'e3d_outputs'/(name+'.stl')
        row=dict(case=name,status='not_executed',error='',face_count='',boundary_loops='',components='',
                 topology_matches_target='',bbox_max_coordinate_change='',self_intersection_status='unverified')
        if path.exists():
            try:
                mesh=load_mesh(path);d=detect_defects(mesh,check_self_intersection=True)
                ref=load_mesh(ROOT/'data'/reference)
                metrics=d.metrics
                bbox=np.asarray([mesh.vertices.min(axis=0),mesh.vertices.max(axis=0)])
                refbbox=np.asarray([ref.vertices.min(axis=0),ref.vertices.max(axis=0)])
                topology_ok=(metrics['topology_passed'] and metrics['boundary_loop_count']==loops and metrics['component_count']==components)
                row.update(status='measured',face_count=len(mesh.faces),boundary_loops=metrics['boundary_loop_count'],
                           components=metrics['component_count'],topology_matches_target=topology_ok,
                           bbox_max_coordinate_change=float(np.max(np.abs(bbox-refbbox))),
                           self_intersection_status=d.self_intersection['status'])
                (out/(name+'_export_diagnosis.json')).write_text(json.dumps(d.to_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as e:row.update(status='failed_to_read_export',error=str(e))
        rows.append(row)
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('Measured:',sum(r['status']=='measured' for r in rows),'Not executed:',sum(r['status']=='not_executed' for r in rows))


if __name__=='__main__':main()
