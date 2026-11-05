"""Fixed same-STL specialist cases; never substitutes a project output for E-3D."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from medical_mesh import MeshAsset,load_mesh,save_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.processing.suggestions import suggest_non_manifold_repairs
from medical_mesh.core.changes import mesh_changes

BASE=ROOT/'results/e3d_complex'


def surface(kind,x,y):
    if kind=='high':return 2*(x*x+.5*y*y)+.65*np.sin(4*x)*np.cos(3*y)
    return .8*(x*x+.4*y*y)+.2*x*y


def annulus(kind):
    n=24
    angles=np.arange(n)*2*np.pi/n
    if kind=='irregular':
        weights=1+.8*np.sin(np.arange(n)*1.7)
        angles=np.r_[0,np.cumsum(weights[:-1])]/weights.sum()*2*np.pi
    radii=.45*np.ones(n)
    if kind=='concave':radii=.42*(1+.35*np.cos(4*angles))
    boundary=np.column_stack((radii*np.cos(angles),radii*np.sin(angles)))
    if kind=='irregular':boundary[:,1]*=.55
    rings=[]
    for t in (0.,.5,1.):
        xy=(1-t)*boundary+t*np.column_stack((np.cos(angles),np.sin(angles)))
        rings.extend(np.column_stack((xy,surface(kind,xy[:,0],xy[:,1]))).tolist())
    faces=[]
    for ring in range(2):
        for i in range(n):
            j=(i+1)%n;a=ring*n+i;b=(ring+1)*n+i;c=(ring+1)*n+j;d=ring*n+j
            faces.extend([[a,b,c],[a,c,d]])
    mesh=MeshAsset(np.asarray(rings),np.asarray(faces,dtype=np.int64))
    # A dense piecewise-linear reference for distance sampling, not a fabricated
    # exact ground-truth triangulation favoring either repair implementation.
    refv=[[0.,0.,float(surface(kind,0.,0.))]]
    nr,nt=24,192
    for r in np.linspace(1/nr,1,nr):
        t=np.arange(nt)*2*np.pi/nt;x=r*np.cos(t);y=r*np.sin(t)
        refv.extend(np.column_stack((x,y,surface(kind,x,y))).tolist())
    reff=[[0,1+i,1+(i+1)%nt] for i in range(nt)]
    for ring in range(nr-1):
        for i in range(nt):
            j=(i+1)%nt;a=1+ring*nt+i;b=a+nt;c=1+(ring+1)*nt+j;d=1+ring*nt+j
            reff.extend([[a,b,c],[a,c,d]])
    return mesh,MeshAsset(np.asarray(refv),np.asarray(reff,dtype=np.int64)),boundary.tolist()


def fixtures():
    e4=MeshAsset(np.array([[0.,0,0],[1,0,0],[.5,1,0],[.5,0,1],[.5,-1,0],[.5,0,-1]]),
        np.array([[0,1,2],[1,0,3],[0,1,4],[1,0,5]]))
    base=load_mesh(ROOT/'data/reference/sphere.npz');v=base.vertices.copy();f=base.faces.copy()
    for fid in (200,700):
        a,b=map(int,base.faces[fid][:2]);p=base.vertices[[a,b]].mean(axis=0);p=p/np.linalg.norm(p)*1.4
        f=np.vstack((f,[a,b,len(v)]));v=np.vstack((v,p))
    multi=base.derive(vertices=v,faces=f)
    pin=load_mesh(ROOT/'data/reference/bowtie_vertex.npz')
    pin_ref,_=repair_mesh(pin,RepairOptions(split_vertex_ids=(0,),check_self_intersection=True))
    mixed=load_mesh(ROOT/'data/damaged/non_manifold_edge.npz');f=mixed.faces[1:].copy()
    f[300]=f[300,[0,2,1]];f=np.vstack((f,f[20],f[30,[0,0,1]]));mixed=mixed.derive(faces=f)
    yield 'c_e4',e4,None,dict(category='nonmanifold',goal='四面共享边；消除异常，保留至少两个面',expected_components=1,minimum_faces=2)
    yield 'c_mnm',multi,base,dict(category='nonmanifold',goal='两处独立非流形边；恢复闭合球面',expected_components=1,expected_loops=0)
    yield 'c_pin',pin,pin_ref,dict(category='nonmanifold',goal='顶点粘连；保留两个壳体',expected_components=2,expected_loops=0,stl_coincident_vertex_limitation=True)
    yield 'c_mix',mixed,base,dict(category='nonmanifold',goal='非流形、缺面、重复、退化、翻面混合',expected_components=1,expected_loops=0)
    for name,kind in [('c_quad','quadric'),('c_conc','concave'),('c_high','high'),('c_irr','irregular')]:
        mesh,reference,boundary=annulus(kind)
        yield name,mesh,reference,dict(category='hole',goal='补内孔，保留外侧天然开口',expected_components=1,expected_loops=1,
            preserve_largest_openings=1,target_polygon_xy=boundary,analytic_surface=kind)


def project_run(name,path,metadata):
    asset=load_mesh(path);current=asset;steps=[];manual_actions=[]
    d=detect_defects(current)
    if metadata['category']=='nonmanifold':
        if any(d.metrics[k] for k in ('duplicate_face_count','degenerate_face_count','orientation_conflict_count')):
            candidate,result=repair_mesh(current,RepairOptions(remove_duplicates=True,remove_degenerate=True,orient_faces=True,check_self_intersection=True))
            steps.append(dict(operation='cleanup',result=result.to_dict()));manual_actions.append('明确勾选重复/退化清理与方向一致化')
            if result.accepted:current=candidate
        d=detect_defects(current)
        if d.metrics['non_manifold_edge_count'] or d.metrics['non_manifold_vertex_count']:
            proposals=suggest_non_manifold_repairs(current,max_candidates=48)
            steps.append(dict(operation='suggest',result=proposals.to_dict()))
            if proposals.metrics['suggestions']:
                plan=proposals.metrics['suggestions'][0]
                candidate,result=repair_mesh(current,RepairOptions(delete_face_ids=plan['delete_face_ids'],split_vertex_ids=plan['split_vertex_ids'],check_self_intersection=True))
                steps.append(dict(operation='selected_first_suggestion',result=result.to_dict()))
                manual_actions.append('按排序选择首个通过复检的方案；不是自主语义决策')
                if result.accepted:current=candidate
        d=detect_defects(current)
        if metadata.get('expected_loops')==0 and not d.metrics['non_manifold_edge_count'] and not d.metrics['non_manifold_vertex_count']:
            targets=tuple(b['id'] for b in d.boundaries if b['kind']=='simple_loop')
            if targets:
                current,result=repair_mesh(current,RepairOptions(fill_boundary_ids=targets,check_self_intersection=True))
                steps.append(dict(operation='declared_artificial_holes',result=result.to_dict()));manual_actions.append('按任务目标显式标记人工孔洞')
    else:
        inner=min(d.boundaries,key=lambda b:b['span'])['id']
        roles={str(b['id']):'repair_target' if b['id']==inner else 'natural' for b in d.boundaries}
        for method in ('planar','quadric'):
            candidate,result=repair_mesh(current,RepairOptions(fill_boundary_ids=(inner,),boundary_roles=roles,hole_method=method,check_self_intersection=True))
            steps.append(dict(operation=method,result=result.to_dict()))
            if result.accepted:current=candidate;break
        manual_actions=['显式标记内孔与天然外边界；平面失败后尝试实验曲面模式']
    out=BASE/'project';out.mkdir(exist_ok=True)
    save_mesh(current,out/(name+'.npz'));save_mesh(current,out/(name+'.stl'))
    native=detect_defects(current,check_self_intersection=True).to_dict()
    roundtrip=detect_defects(load_mesh(out/(name+'.stl')),check_self_intersection=True).to_dict()
    record=dict(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),input_version=asset.version,
        output_version=current.version,manual_actions=manual_actions,steps=steps,native_diagnosis=native,stl_diagnosis=roundtrip,
        geometry_changed=current.geometry_hash()!=asset.geometry_hash())
    (out/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name,'project:',native['metrics']['face_count'],'faces;',native['quality_status'],flush=True)


def main():
    for folder in ('inputs','references','project','vendor_raw','vendor_outputs','evidence'):(BASE/folder).mkdir(parents=True,exist_ok=True)
    records=[]
    for name,mesh,reference,metadata in fixtures():
        path=BASE/'inputs'/(name+'.stl');save_mesh(mesh,path);save_mesh(mesh,path.with_suffix('.npz'))
        if reference is not None:save_mesh(reference,BASE/'references'/(name+'.npz'))
        metadata.update(case=name,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),vendor_status='not_executed')
        records.append(metadata);project_run(name,path,metadata)
    (BASE/'cases.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared 8 complex same-STL cases; vendor results remain unmeasured.')


if __name__=='__main__':main()
