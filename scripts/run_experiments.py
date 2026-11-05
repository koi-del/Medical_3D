"""E1/E2 actual observations and screenshots, never invented success counts."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import csv,json,platform,importlib.metadata
from medical_mesh import detect_defects,repair_mesh,RepairOptions,save_mesh,load_mesh
from medical_mesh.data.synthetic import tetrahedron,sphere,open_tube,two_components,bowtie_vertex,inject_defects


def main():
    out=ROOT/"results"/"E1_E2";out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for kind,key,value in [("hole","boundary_loop_count",1),("duplicate","duplicate_face_count",1),
        ("reverse_duplicate","duplicate_face_count",1),("degenerate","degenerate_face_count",1),
        ("flip","orientation_conflict_count",3),("non_manifold_edge","non_manifold_edge_count",1)]:
        mesh,record=inject_defects(tetrahedron(),kind,seed=17)
        d=detect_defects(mesh,check_self_intersection=True)
        save_mesh(mesh,out/(kind+"_input.npz"))
        (out/(kind+"_diagnosis.json")).write_text(json.dumps(d.to_dict(),indent=2),encoding="utf-8")
        rows.append({"experiment":"E1","case":kind,"metric":key,"expected":value,"observed":d.metrics[key],"passed":d.metrics[key]==value})
    for name,mesh,key,value in [("open_tube",open_tube(),"boundary_loop_count",2),
         ("two_components",two_components(),"component_count",2),("bowtie_vertex",bowtie_vertex(),"non_manifold_vertex_count",1)]:
        d=detect_defects(mesh)
        rows.append({"experiment":"E1","case":name,"metric":key,"expected":value,"observed":d.metrics[key],"passed":d.metrics[key]==value})
    cases=[]
    for kind,options,key in [("duplicate",RepairOptions(remove_duplicates=True),"duplicate_face_count"),
                             ("degenerate",RepairOptions(remove_degenerate=True),"degenerate_face_count"),
                             ("flip",RepairOptions(orient_faces=True),"orientation_conflict_count"),
                             ("hole",RepairOptions(fill_boundary_ids=(0,)),"boundary_loop_count")]:
        damaged,_=inject_defects(tetrahedron(),kind,seed=17)
        cases.append((kind,damaged,options,key,0,True))
    damaged,_=inject_defects(open_tube(),"duplicate",seed=17)
    cases.append(("protect_natural_openings",damaged,RepairOptions(remove_duplicates=True),"boundary_loop_count",2,True))
    damaged,_=inject_defects(two_components(),"duplicate",seed=17)
    cases.append(("protect_two_components",damaged,RepairOptions(remove_duplicates=True),"component_count",2,True))
    damaged,record=inject_defects(tetrahedron(),"non_manifold_edge",seed=17)
    cases.append(("selected_nonmanifold_face",damaged,RepairOptions(delete_face_ids=tuple(record["added_face_ids"])),"non_manifold_edge_count",0,True))
    damaged,_=inject_defects(tetrahedron(),"hole",seed=17)
    cases.append(("oversized_hole_rejected",damaged,RepairOptions(fill_boundary_ids=(0,),max_hole_span=.01),"boundary_loop_count",1,False))
    for name,mesh,options,key,expected,accepted in cases:
        repaired,result=repair_mesh(mesh,options)
        observed=detect_defects(repaired).metrics[key]
        passed=observed==expected and result.accepted==accepted and (accepted or repaired is mesh)
        rows.append({"experiment":"E2","case":name,"metric":key,"expected":expected,"observed":observed,"passed":passed})
        save_mesh(mesh,out/(name+"_before.npz"));save_mesh(repaired,out/(name+"_after.npz"));save_mesh(repaired,out/(name+"_after.stl"))
        (out/(name+"_repair.json")).write_text(json.dumps(result.to_dict(),indent=2),encoding="utf-8")
        try:
            render_pair(mesh,repaired,out/(name+".png"),name)
        except ImportError:
            pass
    with (out/"results.csv").open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    packages={}
    for name in ("numpy","trimesh","pymeshlab","PySide6","pyvista","pyvistaqt","pytest"):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]="not installed"
    (out/"environment.json").write_text(json.dumps({"python":sys.version,"platform":platform.platform(),"packages":packages},indent=2),encoding="utf-8")
    lines=["# E1/E2 实测记录","","固定种子 17；以下结果由脚本实际计算。E1 的拓扑统计基于去重、排除退化面的候选视图，仍保留原面索引。","", "|实验|案例|指标|预期|实测|通过|","|---|---|---|---:|---:|---|"]
    for r in rows:lines.append("|"+"|".join(str(r[k]) for k in ("experiment","case","metric","expected","observed","passed"))+"|")
    lines.extend(["","## 结果解释与边界","", "- 自交是否真正执行见各 diagnosis JSON 的 self_intersection；未执行或组件不可用时为 unverified，不以零代替。",
       "- oversized_hole_rejected 为设计的拒绝案例：超过跨度限值，保留输入版本，错误写入 repair JSON。",
       "- 补洞限于用户指定的简单近共面环，使用投影耳切法，不宣称恢复真实解剖。默认保留所有开口和连通分量。",
       "- 这些是合成几何单元实验，不代表医学样本总体成功率；医学图谱另保留逐模型原始诊断。",
       "- 每个修复案例保存前后 NPZ、STL、实际日志及前后截图，可复算。"])
    (out/"实验报告.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"{sum(r['passed'] for r in rows)}/{len(rows)} E1/E2 observations passed")
    if not all(r["passed"] for r in rows):raise SystemExit(1)


def render_pair(before,after,path,title):
    import pyvista as pv
    import numpy as np
    p=pv.Plotter(shape=(1,2),off_screen=True,window_size=(1200,600))
    for i,mesh in enumerate((before,after)):
        p.subplot(0,i);p.set_background("#172334")
        poly=pv.PolyData(mesh.vertices.copy(),np.column_stack((np.full(len(mesh.faces),3),mesh.faces)).ravel())
        p.add_mesh(poly,color="#95d9d2",show_edges=True,smooth_shading=True,ambient=.15,diffuse=.8)
        d=detect_defects(mesh)
        edges=[e for b in d.boundaries for e in b["edges"]]
        if edges:
            lines=pv.PolyData();lines.points=mesh.vertices.copy();lines.lines=np.column_stack((np.full(len(edges),2),edges)).ravel()
            p.add_mesh(lines,color="#ffd166",line_width=6)
        marked=sorted(set(d.defects["duplicate_face_ids"]+d.defects["degenerate_face_ids"]+
                          [fid for c in d.defects["orientation_conflicts"] for fid in c["face_ids"]]))
        if marked:
            f=mesh.faces[marked]
            p.add_mesh(pv.PolyData(mesh.vertices.copy(),np.column_stack((np.full(len(f),3),f)).ravel()),color="#ff735c",show_edges=True)
        p.add_text(("Before" if i==0 else "After")+f" | faces={len(mesh.faces)} | loops={d.metrics['boundary_loop_count']}",font_size=12,color="white")
        p.view_isometric();p.reset_camera()
    p.link_views();p.screenshot(str(path));p.close()


if __name__=="__main__":main()
