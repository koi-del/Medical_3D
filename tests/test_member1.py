import json
import struct
import numpy as np
import pytest
from medical_mesh import MeshAsset,load_mesh,save_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.core.versions import VersionStore
from medical_mesh.data.synthetic import (tetrahedron,sphere,open_tube,two_components,bowtie_vertex,
                                          inject_defects,intersecting_triangles)
from medical_mesh.processing.mesh_worker import run_job


@pytest.mark.parametrize("factory,components,loops",[(tetrahedron,1,0),(sphere,1,0),(open_tube,1,2),(two_components,2,0)])
def test_reference_topology(factory,components,loops):
    d=detect_defects(factory())
    assert d.metrics["component_count"]==components
    assert d.metrics["boundary_loop_count"]==loops
    assert d.metrics["topology_passed"]
    assert d.self_intersection["face_ids"] is None
    assert d.quality_status=="diagnosed"


@pytest.mark.parametrize("kind,key,expected",[("duplicate","duplicate_face_count",1),
    ("reverse_duplicate","duplicate_face_count",1),("degenerate","degenerate_face_count",1),
    ("hole","boundary_loop_count",1),("non_manifold_edge","non_manifold_edge_count",1),
    ("flip","orientation_conflict_count",3)])
def test_known_defects(kind,key,expected):
    damaged,record=inject_defects(tetrahedron(),kind,seed=17)
    diagnosis=detect_defects(damaged)
    assert diagnosis.metrics[key]==expected
    if kind=="duplicate":
        assert diagnosis.metrics["raw_topology"]["non_manifold_edge_count"]==3
        assert diagnosis.metrics["non_manifold_edge_count"]==0


def test_closed_bowtie_vertex():
    d=detect_defects(bowtie_vertex())
    assert d.metrics["non_manifold_edge_count"]==0
    assert d.metrics["non_manifold_vertex_count"]==1
    assert d.defects["non_manifold_vertices"][0]["sector_count"]==2


@pytest.mark.parametrize("ascii",[True,False])
def test_stl_roundtrip_preserves_defects_and_position(tmp_path,ascii):
    asset,_=inject_defects(tetrahedron((10,20,30)),"duplicate",seed=1)
    path=tmp_path/"模型.stl"
    save_mesh(asset,path,ascii=ascii)
    loaded=load_mesh(path,raw_archive=tmp_path/"raw.npz")
    assert detect_defects(loaded).metrics["duplicate_face_count"]==1
    assert np.array_equal(loaded.vertices.min(axis=0),[10,20,30])
    assert loaded.unit_status=="unknown"
    assert len(load_mesh(tmp_path/"raw.npz").vertices)==len(asset.faces)*3
    assert len(loaded.preprocessing_record[0]["raw_to_canonical"])==len(asset.faces)*3


def test_binary_solid_header(tmp_path):
    path=tmp_path/"solid.stl";save_mesh(tetrahedron(),path)
    data=path.read_bytes();path.write_bytes(b"solid"+data[5:])
    assert len(load_mesh(path).faces)==4


@pytest.mark.parametrize("which",["empty","nan","bad_index","zero_scale","float_index"])
def test_illegal_mesh(which):
    v=tetrahedron().vertices.copy();f=tetrahedron().faces.copy()
    if which=="empty":f=np.empty((0,3),dtype=int)
    if which=="nan":v[0,0]=np.nan
    if which=="bad_index":f[0,0]=99
    if which=="zero_scale":v[:]=0
    if which=="float_index":f=f.astype(float)
    with pytest.raises(ValueError):MeshAsset(v,f)


def test_truncated_and_malformed_stl(tmp_path):
    path=tmp_path/"bad.stl";save_mesh(tetrahedron(),path)
    path.write_bytes(path.read_bytes()[:-2])
    with pytest.raises(ValueError):load_mesh(path)
    path.write_text("solid bad\nfacet normal 0 0 1\nvertex 0 0 0\nendsolid",encoding="ascii")
    with pytest.raises(ValueError):load_mesh(path)


def test_input_immutable_and_reproducible():
    base=sphere()
    a,ra=inject_defects(base,"hole",seed=171,count=4)
    b,rb=inject_defects(base,"hole",seed=171,count=4)
    assert np.array_equal(a.faces,b.faces) and ra==rb
    with pytest.raises(ValueError):base.vertices[0,0]=99
    with pytest.raises(ValueError):base.vertices.flags.writeable=True
    assert len(base.faces)==960


@pytest.mark.parametrize("kind,options,key",[
    ("duplicate",RepairOptions(remove_duplicates=True),"duplicate_face_count"),
    ("degenerate",RepairOptions(remove_degenerate=True),"degenerate_face_count"),
    ("flip",RepairOptions(orient_faces=True),"orientation_conflict_count")])
def test_cleanup_and_orientation(kind,options,key):
    asset,_=inject_defects(tetrahedron(),kind,seed=11)
    mesh,result=repair_mesh(asset,options)
    assert result.status=="completed",result.errors
    assert mesh.parent_version==asset.version
    assert detect_defects(mesh).metrics[key]==0
    assert np.array_equal(mesh.vertices,asset.vertices)


def test_explicit_hole_fill():
    base=tetrahedron();damaged,_=inject_defects(base,"hole",seed=9)
    repaired,result=repair_mesh(damaged,RepairOptions(fill_boundary_ids=(0,)))
    assert result.accepted,result.errors
    assert detect_defects(repaired).metrics["boundary_edge_count"]==0
    assert detect_defects(repaired).metrics["orientation_conflict_count"]==0
    assert len(repaired.faces)==len(base.faces)


def test_natural_opening_and_components_preserved():
    base=open_tube();damaged,_=inject_defects(base,"duplicate",seed=3)
    repaired,result=repair_mesh(damaged,RepairOptions(remove_duplicates=True))
    assert result.accepted,result.errors
    assert detect_defects(repaired).metrics["boundary_loop_count"]==2
    base=two_components();damaged,_=inject_defects(base,"duplicate",seed=3)
    repaired,result=repair_mesh(damaged,RepairOptions(remove_duplicates=True))
    assert result.accepted and detect_defects(repaired).metrics["component_count"]==2


def test_preserve_unselected_loop():
    base=open_tube()
    repaired,result=repair_mesh(base,RepairOptions(fill_boundary_ids=(0,)))
    assert result.accepted,result.errors
    assert detect_defects(repaired).metrics["boundary_loop_count"]==1


def test_nonmanifold_selected_face_repair():
    base=tetrahedron();damaged,record=inject_defects(base,"non_manifold_edge",seed=3)
    repaired,result=repair_mesh(damaged,RepairOptions(delete_face_ids=tuple(record["added_face_ids"])))
    assert result.accepted,result.errors
    assert detect_defects(repaired).metrics["non_manifold_edge_count"]==0


@pytest.mark.parametrize("options",[RepairOptions(),RepairOptions(fill_boundary_ids=(99,)),
    RepairOptions(fill_boundary_ids=(0,),max_hole_span=.01),RepairOptions(delete_face_ids=(0,1,2,3))])
def test_rejection_keeps_original(options):
    base=open_tube() if options.fill_boundary_ids else tetrahedron()
    repaired,result=repair_mesh(base,options)
    assert result.status=="rejected"
    assert repaired is base and result.output_version==base.version
    assert result.errors


def test_version_store_rollback_and_notifications(tmp_path):
    store=VersionStore(tmp_path);events=[];store.subscribe(events.append)
    base=tetrahedron();store.commit(base)
    changed=base.derive(faces=base.faces[:-1]);store.commit(changed)
    assert store.rollback().version==base.version
    assert events==[base.version,changed.version,base.version]
    assert VersionStore(tmp_path).get().geometry_hash()==base.geometry_hash()
    assert (tmp_path/(changed.version+".npz")).exists()
    with pytest.raises(ValueError):store.get("../oops")


def test_worker_success_and_failure(tmp_path):
    path=tmp_path/"mesh.npz";save_mesh(tetrahedron(),path)
    result=run_job({"operation":"diagnose","input_path":str(path),"output_dir":str(tmp_path/"ok")})
    assert result["status"]=="completed"
    result=run_job({"operation":"diagnose","input_path":"not_there.stl","output_dir":str(tmp_path/"failed")})
    assert result["status"]=="failed" and result["errors"]
    assert (tmp_path/"failed"/"result.json").exists()


def test_self_check_real_backend():
    pytest.importorskip("pymeshlab")
    d=detect_defects(intersecting_triangles(),check_self_intersection=True)
    assert d.self_intersection["status"]=="verified",d.self_intersection
    assert set(d.self_intersection["face_ids"])=={0,1}
    d=detect_defects(tetrahedron(),check_self_intersection=True)
    assert d.self_intersection["status"]=="verified"
    assert d.self_intersection["face_ids"]==[]


def test_self_check_unavailable_is_not_zero(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules,"pymeshlab",None)
    asset=tetrahedron()
    d=detect_defects(asset,check_self_intersection=True)
    assert d.self_intersection["status"]=="unverified"
    assert d.self_intersection["face_ids"] is None
    damaged,_=inject_defects(asset,"duplicate")
    candidate,result=repair_mesh(damaged,RepairOptions(remove_duplicates=True,check_self_intersection=True))
    assert candidate is damaged and result.status=="rejected"


def test_nonplanar_loop_rejected():
    asset=open_tube()
    vertices=asset.vertices.copy();vertices[0,2]+=.5
    asset=asset.derive(vertices=vertices)
    candidate,result=repair_mesh(asset,RepairOptions(fill_boundary_ids=(0,)))
    assert candidate is asset and result.status=="rejected"
    assert "Nonplanar" in result.errors[0]


def test_concave_loop_ear_clipping():
    xy=np.array([[0,0],[2,0],[2,2],[1,1],[0,2]],float)
    vertices=np.vstack((np.column_stack((xy,np.zeros(5))),np.column_stack((xy,np.ones(5)))))
    faces=[[3,1,0],[3,2,1],[4,3,0]]
    for i in range(5):
        j=(i+1)%5
        faces.extend([[i,j,j+5],[i,j+5,i+5]])
    asset=MeshAsset(vertices,np.array(faces))
    d=detect_defects(asset)
    assert d.metrics["boundary_loop_count"]==1
    candidate,result=repair_mesh(asset,RepairOptions(fill_boundary_ids=(0,)))
    assert result.accepted,result.errors
    after=detect_defects(candidate)
    assert after.metrics["boundary_edge_count"]==0
    assert after.metrics["orientation_conflict_count"]==0
    assert len(candidate.faces)==16


def test_remove_whole_component_rejected():
    asset=two_components()
    candidate,result=repair_mesh(asset,RepairOptions(delete_face_ids=(0,1,2,3)))
    assert candidate is asset and result.status=="rejected"
    assert "component" in result.errors[0]


def test_uppercase_npz_and_metadata_roundtrip(tmp_path):
    asset=tetrahedron((10,20,30))
    path=tmp_path/"mesh.NPZ";save_mesh(asset,path)
    loaded=load_mesh(path)
    assert loaded.metadata()==asset.metadata()
    assert loaded.geometry_hash()==asset.geometry_hash()


def test_confirm_units_without_moving_coordinates(tmp_path):
    path=tmp_path/"mesh.stl";save_mesh(tetrahedron((10,20,30)),path)
    asset=load_mesh(path,source_unit="cm",unit_to_mm=10)
    assert asset.unit_status=="confirmed" and asset.unit_to_mm==10
    assert np.array_equal(asset.vertices.min(axis=0),[10,20,30])
    with pytest.raises(ValueError):load_mesh(path,source_unit="cm")
