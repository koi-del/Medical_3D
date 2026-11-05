"""Real FreeCAD matrix: 4 geometries x 6 directions + unit and failure tests."""
import argparse
import csv
from datetime import datetime
import html
import json
from pathlib import Path
import sys
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
import numpy as np

from medical_mesh.member2.cad.runner import convert_file, effective_config, run_worker
from medical_mesh.member2.core.model import write_json, file_hash
from medical_mesh.member2.reporting import render_report

PAIRS = [("stl", "step"), ("stl", "igs"), ("step", "stl"),
         ("igs", "stl"), ("step", "igs"), ("igs", "step")]


def build_report(root, runtime, config, rows, negatives, unit_result):
    with (root/"conversion_matrix.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = {"runtime": runtime, "config": config, "cases": rows,
               "positive_passed": sum(r["passed"] for r in rows), "positive_total": len(rows),
               "negative_cases": negatives, "negative_passed": sum(r["passed"] for r in negatives),
               "cm_to_mm": unit_result,
               "all_passed": all(r["passed"] for r in rows+negatives) and unit_result["passed"]}
    write_json(root/"summary.json", summary)
    esc = lambda x: html.escape(str(x))
    headers = ["样本", "方向", "结果", "实际类型", "D95 mm", "采样最大 mm", "坐标偏差 mm", "离散稳定性 mm", "详情"]
    body = "<table><thead><tr>"+"".join(f"<th>{h}</th>" for h in headers)+"</tr></thead><tbody>"
    for row in rows:
        values = [row["case"], row["direction"], "通过" if row["passed"] else "失败", row["representation"],
                  row["d95_mm"], row["sampled_max_mm"], row["bbox_delta_mm"], row["convergence_delta_mm"]]
        body += "<tr>"+"".join(f"<td>{esc(format(x,'.6g') if isinstance(x,float) else x)}</td>" for x in values)
        body += f'<td><a href="{esc(row["report"])}">报告</a></td></tr>'
    body += "</tbody></table>"
    checks = "<ul>"+"".join(f'<li>{esc(x["case"])}：{"通过" if x["passed"] else "失败"}（{esc(x["status"])}）</li>' for x in negatives)+"</ul>"
    text = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>FreeCAD六向转换验证</title>
<style>body{{font:15px/1.7 -apple-system,sans-serif;max-width:1250px;margin:40px auto;padding:0 24px;color:#22303d}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d4dce0;padding:8px;text-align:left}}
th{{background:#eaf0f3}}tr:nth-child(even){{background:#f8fafb}}pre{{overflow:auto;background:#f4f6f8;padding:16px}}</style>
<h1>FreeCAD六向格式转换与回读验证</h1><p>4类合成几何，6个方向；共{len(rows)}项，{summary["positive_passed"]}项通过。
FreeCAD {esc('.'.join(runtime['freecad_version'][:3]))}，OpenCASCADE {esc(runtime.get('occ_version'))}。</p>
<p>每项独立导出、新进程两档回读，检查包围盒坐标、双向采样表面偏差和离散稳定性。无ICP、自动居中或自动缩放。
数据为自生成CAD，未宣称医学模型或NX兼容验证。STL转CAD采用面片曲面策略，不恢复建模历史。</p>
{body}<h2>单位验证</h2><p>厘米STL按10倍转换为毫米：{esc(unit_result['passed'])}。</p>
<h2>预期拒绝与失败</h2>{checks}<h2>冻结配置</h2><pre>{esc(json.dumps(config,ensure_ascii=False,indent=2))}</pre>
<p>所有表面误差为有限采样估计，非严格最大偏差。CAD输入参考为细离散代理；两档稳定性是经验检查。
同一OpenCASCADE内核回读不代表所有CAD软件兼容。实际几何类型按回读记录，曲面不能称为实体。</p></html>'''
    (root/"report.html").write_text(text, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=f"runs/cad_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:4]}")
    parser.add_argument("--config")
    args = parser.parse_args()
    root = Path(args.out).resolve()
    if root.exists():
        parser.error("choose a fresh output directory")
    root.mkdir(parents=True)
    config = effective_config(json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else {})
    config["write_error_figure"] = False
    write_json(root/"frozen_config.json", config)
    runtime = run_worker(config, {"mode": "probe"}, root, "runtime")
    generated = run_worker(config, {"mode": "fixtures", "fixture_dir": str(root/"fixtures")}, root, "fixtures")
    rows = []
    for fixture in generated["manifest"]:
        for src, target in PAIRS:
            direction = src+"_to_"+target
            directory = root/fixture["case"]/direction
            print(f'[{len(rows)+1}/24] {fixture["case"]} {src}->{target}', flush=True)
            result = convert_file(fixture["paths"][src], target, config, directory, "mm" if src == "stl" else None)
            render_report(result, directory)
            metrics = result.get("metrics", {})
            passed = result.get("geometry_status") == "passed" and result.get("status") == "completed"
            rows.append({"case": fixture["case"], "direction": direction, "passed": passed,
                         "status": result["status"], "representation": result.get("actual_representation"),
                         "d95_mm": metrics.get("d95"), "sampled_max_mm": metrics.get("sampled_max"),
                         "bbox_delta_mm": result.get("bbox_max_delta_mm"), "convergence_delta_mm": result.get("convergence_delta_mm"),
                         "output_sha256": result.get("output_sha256"), "report": str((directory/"report.html").relative_to(root)),
                         "errors": ";".join(result.get("errors", result.get("reason_codes", [])))})
            print("  "+("PASS" if passed else "FAIL "+rows[-1]["errors"]), flush=True)
    source = generated["manifest"][0]["paths"]["stl"]
    negatives = []
    negative_configs = [
        ("unknown_stl_unit", {}, None, source, "step", "failed"),
        ("face_budget", {"max_stl_faces": 1}, "mm", source, "step", "failed"),
        ("unqualified_solid", {"representation": "solid"}, "mm", source, "step", "failed"),
        ("invalid_tessellation", {"linear_deflection_mm": -1}, "mm", source, "step", "failed"),
        ("same_format", {}, "mm", source, "stl", "failed"),
        ("timeout", {"timeout_seconds": .001}, "mm", source, "step", "timeout"),
    ]
    corrupt = root/"invalid.step"; corrupt.write_text("NOT A STEP FILE")
    negative_configs.append(("corrupt_step", {}, None, str(corrupt), "stl", "failed"))
    legacy = root/"fixtures/sphere/legacy_periodic.igs"
    negative_configs.append(("degenerate_periodic_iges", {}, None, str(legacy), "step", "failed"))
    for name, overrides, unit, file, target, expected in negative_configs:
        print("[negative] "+name, flush=True)
        result = convert_file(file, target, {**config, **overrides}, root/"negative"/name, unit)
        negatives.append({"case": name, "status": result["status"], "passed": result["status"] == expected,
                          "errors": result.get("errors", [])})
    import trimesh
    mesh = trimesh.load_mesh(source, process=False)
    mesh.vertices /= 10
    cm_path = root/"centimeters.stl"; mesh.export(str(cm_path))
    result = convert_file(cm_path, "step", config, root/"unit_cm_to_mm", "cm")
    expected = generated["manifest"][0]["cad"]["bbox_mm"]
    unit_result = {"passed": result.get("geometry_status") == "passed" and
                   np.allclose(result.get("readback", {}).get("bbox_mm"), expected, atol=1e-5, rtol=0),
                   "expected_bbox_mm": expected, "actual_bbox_mm": result.get("readback", {}).get("bbox_mm"),
                   "status": result["status"], "factor": result.get("unit_transform", {}).get("factor_to_mm")}
    summary = build_report(root, runtime, config, rows, negatives, unit_result)
    print(json.dumps({"all_passed": summary["all_passed"], "positive": f'{summary["positive_passed"]}/24',
                      "negative": f'{summary["negative_passed"]}/{len(negatives)}', "cm_to_mm": unit_result["passed"],
                      "report": str(root/"report.html")}, ensure_ascii=False), flush=True)
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
