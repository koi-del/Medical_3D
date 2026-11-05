"""Independent export audit plus explicitly sampled point-to-triangle distances."""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
import numpy as np
import pyvista as pv
from matplotlib.path import Path as Polygon
from vtkmodules.vtkCommonCore import reference
from vtkmodules.vtkCommonDataModel import vtkStaticCellLocator

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from medical_mesh import load_mesh,detect_defects
from medical_mesh.core.changes import mesh_changes
BASE=ROOT/'results/e3d_complex'


def dataset(asset):
    return pv.PolyData(asset.vertices.copy(),np.column_stack((np.full(len(asset.faces),3),asset.faces)).ravel())


def distances(points,target):
    locator=vtkStaticCellLocator();locator.SetDataSet(target);locator.BuildLocator()
    closest=[0.,0.,0.];cell=reference(0);sub=reference(0);squared=reference(0.)
    values=[]
    for point in points:
        locator.FindClosestPoint(point,closest,cell,sub,squared);values.append(float(squared)**.5)
    return np.asarray(values)


def samples(asset,polygon=None):
    t=asset.vertices[asset.faces]
    points=np.vstack((asset.vertices[np.unique(asset.faces)],t.mean(axis=1),((t[:,0]+t[:,1])/2),((t[:,1]+t[:,2])/2),((t[:,2]+t[:,0])/2)))
    if polygon is not None:points=points[Polygon(polygon).contains_points(points[:,:2],radius=-1e-8)]
    if len(points)>4000:points=points[np.linspace(0,len(points)-1,4000,dtype=int)]
    return points


def distance_summary(points,target):
    if not len(points):return dict(status='no_interior_samples',sample_count=0,mean=None,rms=None,maximum=None)
    values=distances(points,dataset(target))
    return dict(status='measured',sample_count=len(values),mean=float(values.mean()),
                rms=float(np.sqrt(np.mean(values**2))),maximum=float(values.max()))


def boundary_lines(asset,boundary):
    edges=np.asarray(boundary['edges']);mesh=pv.PolyData();mesh.points=asset.vertices.copy()
    mesh.lines=np.column_stack((np.full(len(edges),2),edges)).ravel();return mesh


def evaluate(asset,case,input_asset):
    diagnosis=detect_defects(asset,check_self_intersection=True).to_dict();m=diagnosis['metrics']
    passed=m['topology_passed'] and diagnosis['self_intersection']['status']=='verified' and not diagnosis['self_intersection']['face_ids']
    passed=passed and m['component_count']==case['expected_components'] and len(asset.faces)>=case.get('minimum_faces',1)
    if 'expected_loops' in case:passed=passed and m['boundary_loop_count']==case['expected_loops']
    preserved=None
    if case['category']=='hole':
        before=detect_defects(input_asset).boundaries;outer=max(before,key=lambda b:b['span'])
        preserved=False
        if len(diagnosis['boundaries'])==1 and diagnosis['boundaries'][0]['kind']=='simple_loop':
            actual=diagnosis['boundaries'][0]
            a=distances(input_asset.vertices[outer['vertex_ids']],boundary_lines(asset,actual))
            b=distances(asset.vertices[actual['vertex_ids']],boundary_lines(input_asset,outer))
            preserved=bool(max(a.max(),b.max())<=1e-5*m['bbox_diagonal'])
        passed=passed and preserved
    record=dict(diagnosis=diagnosis,goal_passed=bool(passed),natural_outer_rim_preserved=preserved,
                changes=mesh_changes(input_asset,asset))
    ref_path=BASE/'references'/(case['case']+'.npz')
    if ref_path.exists():
        ref=load_mesh(ref_path);polygon=case.get('target_polygon_xy')
        record['sampled_distance']=dict(reference_to_output=distance_summary(samples(ref,polygon),asset),
            output_to_reference=distance_summary(samples(asset,polygon),ref),
            scope='Deterministic vertices/centroids/edge-midpoints, at most 4000 per direction. Hole cases restrict samples to target polygon interior. Sampled maximum is NOT exact Hausdorff distance or clinical error.',
            reference_sha256=hashlib.sha256(ref_path.read_bytes()).hexdigest())
    return record


def main():
    cases=json.loads((BASE/'cases.json').read_text(encoding='utf-8'));rows=[]
    for case in cases:
        name=case['case'];input_path=BASE/'inputs'/(name+'.stl');input_asset=load_mesh(input_path)
        if hashlib.sha256(input_path.read_bytes()).hexdigest()!=case['input_sha256']:raise RuntimeError('Input hash changed')
        for engine in ('project_native','project_stl','vendor'):
            path=(BASE/'project'/(name+('.npz' if engine=='project_native' else '.stl')))
            row=dict(case=name,engine=engine,status='not_exported',face_count='',boundary_loops='',components='',
                     goal_passed='',outer_rim_preserved='',reference_to_output_rms='',output_to_reference_rms='',error='')
            if engine=='vendor':
                prefixes=['自动修复-'] if not case.get('vendor_method') else ['填充空洞-','手动修复-']
                candidates=[p for p in (BASE/'vendor_raw').glob('*.stl') if p.stem.replace(' ','') in [prefix+name for prefix in prefixes]]
                if len(candidates)>1:raise RuntimeError('Ambiguous vendor export')
                path=candidates[0] if candidates else BASE/'vendor_outputs'/(name+'.stl')
            if path.exists():
                try:
                    asset=load_mesh(path);record=evaluate(asset,case,input_asset)
                    record.update(case=name,engine=engine,file=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),input_sha256=case['input_sha256'])
                    (BASE/(name+'_'+engine+'_audit.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                    m=record['diagnosis']['metrics'];error=record.get('sampled_distance',{})
                    row.update(status='measured',face_count=len(asset.faces),boundary_loops=m['boundary_loop_count'],components=m['component_count'],
                        goal_passed=record['goal_passed'],outer_rim_preserved=record['natural_outer_rim_preserved'],
                        reference_to_output_rms=error.get('reference_to_output',{}).get('rms'),output_to_reference_rms=error.get('output_to_reference',{}).get('rms'))
                    if engine=='vendor':
                        target=BASE/'vendor_outputs'/(name+'.stl')
                        if path.resolve()!=target.resolve():shutil.copy2(path,target)
                except Exception as exc:row.update(status='audit_failed',error=str(exc))
            rows.append(row)
        print(name,[(r['engine'],r['status'],r['goal_passed']) for r in rows[-3:]],flush=True)
    with (BASE/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


if __name__=='__main__':main()
