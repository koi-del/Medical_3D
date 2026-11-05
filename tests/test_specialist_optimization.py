import json
from pathlib import Path
import numpy as np
import pytest
from medical_mesh import MeshAsset,load_mesh,save_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.processing.suggestions import suggest_non_manifold_repairs

ROOT=Path(__file__).resolve().parents[1]


def annulus(n):
    angle=np.arange(n)*2*np.pi/n
    radius=.4*(1+.3*np.cos(3*angle))
    inside=np.column_stack((radius*np.cos(angle),radius*np.sin(angle)))
    outside=np.column_stack((np.cos(angle),np.sin(angle)))
    points=[];faces=[]
    for fraction in (0,.5,1):
        xy=(1-fraction)*inside+fraction*outside;x,y=xy.T
        points.extend(np.column_stack((x,y,.6*x*x+.3*y*y+.15*x*y)))
    for ring in range(2):
        for i in range(n):
            j=(i+1)%n;a=ring*n+i;b=a+n;c=(ring+1)*n+j;d=ring*n+j
            faces.extend(([a,b,c],[a,c,d]))
    # A rotated, translated and scaled shape, independent of the benchmark cases.
    rotation,_=np.linalg.qr(np.random.default_rng(91).normal(size=(3,3)))
    return MeshAsset(np.asarray(points)@rotation*2.3+[4,-2,8],np.asarray(faces,dtype=np.int64))


@pytest.mark.parametrize('n',[18,27])
def test_curved_concave_patch_fixes_only_target_and_preserves_coordinates(n,tmp_path):
    asset=annulus(n);d=detect_defects(asset);inner=min(d.boundaries,key=lambda b:b['span'])['id']
    roles={str(b['id']):'repair_target' if b['id']==inner else 'natural' for b in d.boundaries}
    out,result=repair_mesh(asset,RepairOptions(fill_boundary_ids=(inner,),hole_method='surface',
        boundary_roles=roles,check_self_intersection=True))
    assert result.accepted,result.errors
    assert np.array_equal(out.vertices[:len(asset.vertices)],asset.vertices)
    assert np.array_equal(out.faces[:len(asset.faces)],asset.faces)
    assert result.diagnosis_after['metrics']['topology_passed']
    assert result.diagnosis_after['metrics']['boundary_loop_count']==1
    assert result.diagnosis_after['self_intersection']['status']=='verified'
    assert result.operations[-1]['added_vertex_count']>0
    assert result.operations[-1]['minimum_angle_after_degrees']>=result.operations[-1]['minimum_angle_before_degrees']-1e-8
    save_mesh(out,tmp_path/'cap.stl')
    assert detect_defects(load_mesh(tmp_path/'cap.stl')).metrics['topology_passed']


def test_curved_mode_requires_self_check_and_respects_natural_role():
    asset=annulus(18);d=detect_defects(asset);inner=min(d.boundaries,key=lambda b:b['span'])['id']
    for check,roles in [(False,{}),(True,{str(b['id']):'natural' for b in d.boundaries})]:
        out,result=repair_mesh(asset,RepairOptions(fill_boundary_ids=(inner,),hole_method='surface',
            boundary_roles=roles,check_self_intersection=check))
        assert out is asset and not result.accepted


def test_three_nonmanifold_regions_without_face_number_assumptions():
    base=load_mesh(ROOT/'data/reference/sphere.npz');vertices=base.vertices.copy();faces=base.faces.copy()
    for fid in (50,350,710):
        a,b=map(int,base.faces[fid][:2]);p=base.vertices[[a,b]].mean(axis=0)
        faces=np.vstack((faces,[a,b,len(vertices)]));vertices=np.vstack((vertices,p/np.linalg.norm(p)*1.4))
    faces=faces[np.random.default_rng(3).permutation(len(faces))]
    asset=base.derive(vertices=vertices,faces=faces)
    proposals=suggest_non_manifold_repairs(asset,max_candidates=12)
    assert proposals.metrics['examined']<=12
    assert proposals.metrics['suggestions']
    first=proposals.metrics['suggestions'][0]
    out,result=repair_mesh(asset,RepairOptions(delete_face_ids=first['delete_face_ids'],check_self_intersection=True))
    assert result.accepted and len(out.faces)==len(base.faces)
    assert result.diagnosis_after['metrics']['boundary_loop_count']==0
    assert result.diagnosis_after['metrics']['topology_passed']


def test_stl_roundtrip_audit_detects_vertex_split_loss(tmp_path):
    asset=load_mesh(ROOT/'data/reference/bowtie_vertex.npz')
    out,result=repair_mesh(asset,RepairOptions(split_vertex_ids=(0,),check_self_intersection=True))
    assert result.accepted
    save_mesh(out,tmp_path/'pin.stl')
    audit=json.loads((tmp_path/'pin.stl.json').read_text(encoding='utf-8'))['export_validation']
    assert audit['status']=='checked' and not audit['topology_passed']
    assert audit['changed_metrics']['non_manifold_vertex_count']['after']>0
    assert audit['warnings'] and audit['self_intersection_status']=='unverified'


def test_stl_roundtrip_does_not_claim_success_after_float32_collapse(tmp_path):
    asset=MeshAsset(np.array([[1e8,0,0],[1e8+1,0,0],[1e8,1,0]]),np.array([[0,1,2]]))
    save_mesh(asset,tmp_path/'collapse.stl')
    audit=json.loads((tmp_path/'collapse.stl.json').read_text(encoding='utf-8'))['export_validation']
    assert not audit['topology_passed'] and audit['warnings']


def test_separate_shell_export_preserves_touching_closed_shells(tmp_path):
    import hashlib
    import zipfile
    from medical_mesh.io.shell_set import save_shell_set
    asset=load_mesh(ROOT/'data/reference/bowtie_vertex.npz')
    out,result=repair_mesh(asset,RepairOptions(split_vertex_ids=(0,),check_self_intersection=True))
    assert result.accepted
    destination=tmp_path/'pin.stlset.zip';manifest=save_shell_set(out,destination)
    assert len(manifest['shells'])==2
    assert sorted(fid for entry in manifest['shells'] for fid in entry['input_face_ids'])==list(range(8))
    with zipfile.ZipFile(destination) as archive:
        assert json.loads(archive.read('manifest.json'))['geometry_hash']==out.geometry_hash()
        for entry in manifest['shells']:
            content=archive.read(entry['file'])
            assert hashlib.sha256(content).hexdigest()==entry['sha256']
            file=tmp_path/entry['file'];file.write_bytes(content)
            mesh=load_mesh(file);diagnosis=detect_defects(mesh,check_self_intersection=True)
            assert len(mesh.faces)==4 and diagnosis.quality_status=='verified_closed_surface'
            assert np.array_equal(np.unique(mesh.vertices,axis=0),np.unique(out.vertices[out.faces[entry['input_face_ids']]].reshape(-1,3),axis=0))


def test_separate_shell_export_falls_back_to_ascii_without_moving_model(tmp_path):
    from medical_mesh.io.shell_set import save_shell_set
    asset=load_mesh(ROOT/'data/reference/tetrahedron.npz')
    translated=asset.derive(vertices=asset.vertices+[1e8,0,0])
    manifest=save_shell_set(translated,tmp_path/'large.stlset.zip')
    assert manifest['shells'][0]['encoding']=='ascii_float64'
    assert manifest['shells'][0]['diagnosis']['quality_status']=='verified_closed_surface'


def test_separate_shell_export_rejects_unrepaired_input(tmp_path):
    from medical_mesh.io.shell_set import save_shell_set
    asset=load_mesh(ROOT/'data/reference/bowtie_vertex.npz')
    destination=tmp_path/'bad.stlset.zip'
    with pytest.raises(ValueError,match='复检通过'):save_shell_set(asset,destination)
    assert not destination.exists()
