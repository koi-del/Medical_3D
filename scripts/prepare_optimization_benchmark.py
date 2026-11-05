"""Same-input optimization trials. Vendor outputs are never synthesized."""
import hashlib,json
from pathlib import Path
import numpy as np
from medical_mesh import load_mesh,save_mesh,MeshAsset
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/e3d_optimization'


def main():
    if (BASE/'cases.json').exists():raise RuntimeError('Existing benchmark inputs must not be overwritten')
    for name in ('inputs','references','project_before','project_after','vendor_raw','evidence'):(BASE/name).mkdir(parents=True,exist_ok=True)
    sphere=load_mesh(ROOT/'data/reference/sphere.npz')
    sphere=sphere.derive(vertices=sphere.vertices*15)
    rng=np.random.default_rng(20261104)
    noise=sphere.derive(vertices=sphere.vertices*(1+rng.normal(0,.008,(len(sphere.vertices),1))))
    kidney=load_mesh(ROOT/'data/medical/FMA7204.stl')
    n=17;x,y=np.meshgrid(np.linspace(-2,2,n),np.linspace(-2,2,n));z=.15*np.sin(x)*np.cos(y)
    points=np.column_stack((x.ravel(),y.ravel(),z.ravel()));faces=[]
    for i in range(n-1):
        for j in range(n-1):
            a=i*n+j;faces.extend(([a,a+1,a+n+1],[a,a+n+1,a+n]))
    patch=MeshAsset(points,np.asarray(faces,dtype=np.int64));noisy=points.copy()
    variation=rng.normal(0,.04,(n,n));variation[[0,-1],:]=0;variation[:,[0,-1]]=0;noisy[:,2]+=variation.ravel()
    cases=[('o_s50',sphere,sphere,'qem',{'keep_ratio':.5}),('o_s20',sphere,sphere,'qem',{'keep_ratio':.2}),
           ('o_k20',kidney,kidney,'qem',{'keep_ratio':.2}),
           ('o_closed',noise,sphere,'taubin',{'iterations':5}),
           ('o_open',patch.derive(vertices=noisy),patch,'taubin',{'iterations':5}),
           ('o_remesh',sphere,sphere,'remesh',{'target_edge_length':3.,'iterations':3})]
    records=[]
    for name,asset,reference,operation,parameters in cases:
        path=BASE/'inputs'/(name+'.stl');save_mesh(asset,path);save_mesh(reference,BASE/'references'/(name+'.npz'))
        records.append(dict(case=name,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),operation=operation,
            parameters=parameters,input_faces=len(asset.faces),unit_status=asset.unit_status,
            reference_kind='synthetic_clean_surface' if name in ('o_closed','o_open') else 'same_input_shape',
            status='awaiting_vendor_test'))
    (BASE/'cases.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared',len(records),'same-input trials')


if __name__=='__main__':main()
