import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import csv,json
from medical_mesh import load_mesh,save_mesh,detect_defects,repair_mesh,RepairOptions
from medical_mesh.data.synthetic import inject_defects
from run_experiments import render_pair


def main():
    out=ROOT/"results"/"medical_E1_E2";out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path in sorted((ROOT/"data"/"medical").glob("*.stl")):
        base=load_mesh(path)
        original=detect_defects(base,check_self_intersection=True)
        (out/(path.stem+"_original_diagnosis.json")).write_text(json.dumps(original.to_dict(),indent=2),encoding="utf-8")
        for kind,metric,expected,options in [
            ("duplicate","duplicate_face_count",1,RepairOptions(remove_duplicates=True)),
            ("degenerate","degenerate_face_count",1,RepairOptions(remove_degenerate=True)),
            ("flip","orientation_conflict_count",3,RepairOptions(orient_faces=True)),
            ("hole","boundary_loop_count",1,RepairOptions(fill_boundary_ids=(0,),max_hole_span=25))]:
            damaged,record=inject_defects(base,kind,seed=20261016)
            before=detect_defects(damaged)
            repaired,result=repair_mesh(damaged,options)
            after=detect_defects(repaired)
            observed=before.metrics[metric]-original.metrics[metric]
            passed=observed==expected and result.accepted and after.metrics[metric]==original.metrics[metric]
            case=path.stem+"_"+kind
            rows.append({"model":path.stem,"kind":kind,"metric":metric,"expected_added":expected,
                         "observed_added":observed,"original":original.metrics[metric],"before":before.metrics[metric],
                         "after":after.metrics[metric],"repair_status":result.status,"passed":passed,
                         "original_self_intersection_status":original.self_intersection["status"]})
            save_mesh(damaged,out/(case+"_before.npz"));save_mesh(repaired,out/(case+"_after.npz"))
            save_mesh(repaired,out/(case+"_after.stl"))
            (out/(case+"_injection.json")).write_text(json.dumps(record,indent=2),encoding="utf-8")
            (out/(case+"_repair.json")).write_text(json.dumps(result.to_dict(),indent=2),encoding="utf-8")
            if kind=="hole":render_pair(damaged,repaired,out/(case+".png"),case)
            print(case,result.status,passed,flush=True)
    with (out/"results.csv").open("w",encoding="utf-8-sig",newline="") as file:
        w=csv.DictWriter(file,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    lines=["# 医学图谱 E1/E2 外部验证","","数据为 BodyParts3D 3.0 同一男性图谱中的三个器官，不是三个独立患者。单位未确认，保留原始坐标。缺陷为人工注入，不代表原模型自带这些缺陷。","",
           "|模型|注入类型|预期增量|实测增量|修复前|修复后|状态|通过|","|---|---|---:|---:|---:|---:|---|---|"]
    for r in rows:lines.append("|"+"|".join(str(r[k]) for k in ("model","kind","expected_added","observed_added","before","after","repair_status","passed"))+"|")
    lines.extend(["","每个模型的原始自交结果单列保存。修复测试默认只校验拓扑，不能据此推断所有医学几何均无自交。",
                  "补洞仅选择人工删除单个三角面所产生的环，原始局部面保存在 injection JSON。跨度限值25使用原坐标单位。",
                  "衍生医学网格继续适用 CC BY-SA 2.1 Japan，署名见 THIRD_PARTY_NOTICES.md。"])
    (out/"医学模型实验报告.md").write_text("\n".join(lines),encoding="utf-8")
    if not all(r["passed"] for r in rows):raise SystemExit(1)


if __name__=="__main__":main()
