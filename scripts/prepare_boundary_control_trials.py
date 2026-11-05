"""Disambiguate E-3D's largest-hole selection without changing rim shape."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from medical_mesh import load_mesh,save_mesh,detect_defects
from prepare_complex_benchmark import BASE,project_run

cases=json.loads((BASE/'cases.json').read_text(encoding='utf-8'))
for original_name,name in [('c_quad','c_q2'),('c_conc','c_c2'),('c_high','c_h2'),('c_irr','c_i2')]:
    if any(c['case']==name for c in cases):continue
    original=next(c for c in cases if c['case']==original_name)
    mesh=load_mesh(BASE/'inputs'/(original_name+'.stl'))
    outer=max(detect_defects(mesh).boundaries,key=lambda b:b['span'])
    outer_edges={tuple(sorted(edge)) for edge in outer['edges']}
    vertices=mesh.vertices.tolist();faces=[]
    for triangle in mesh.faces:
        for i in range(3):
            a,b,c=map(int,(triangle[i],triangle[(i+1)%3],triangle[(i+2)%3]))
            if tuple(sorted((a,b))) in outer_edges:
                mid=len(vertices);vertices.append(((mesh.vertices[a]+mesh.vertices[b])/2).tolist())
                faces.extend([[a,mid,c],[mid,b,c]]);break
        else:faces.append(triangle.tolist())
    controlled=mesh.derive(vertices=np.asarray(vertices),faces=np.asarray(faces,dtype=np.int64))
    path=BASE/'inputs'/(name+'.stl');save_mesh(controlled,path);save_mesh(controlled,path.with_suffix('.npz'))
    reference=BASE/'references'/(name+'.npz');reference.write_bytes((BASE/'references'/(original_name+'.npz')).read_bytes())
    trial={**original,'case':name,'variant_of':original_name,'outer_edge_count':48,'inner_edge_count':24,
           'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'vendor_status':'not_executed'}
    if name=='c_h2':trial['vendor_method']='manual_curvature_trial'
    cases.append(trial);project_run(name,path,trial)
(BASE/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
print('Added four outer-rim edge-count control trials; original eight cases are unchanged.')
