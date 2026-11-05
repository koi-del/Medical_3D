import csv
import html
import json
from pathlib import Path
import numpy as np
from medical_mesh.core.model import write_json


def error_figure(details, path):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    limit = max(float(details["distances_ab"].max()), float(details["distances_ba"].max()), 1e-12)
    fig = plt.figure(figsize=(10, 4), layout="constrained")
    for index, (points, distance, title) in enumerate((("points_ab", "distances_ab", "Reference to candidate"),
                                                     ("points_ba", "distances_ba", "Candidate to reference"))):
        ax = fig.add_subplot(1, 2, index+1, projection="3d")
        stride = max(1, len(details[points])//3000)
        cloud = details[points][::stride]
        mappable = ax.scatter(*cloud.T, c=details[distance][::stride], s=2, vmin=0, vmax=limit, cmap="viridis")
        ax.set_title(title)
        ax.set_box_aspect(np.maximum(np.ptp(details[points], axis=0), 1e-6))
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    fig.colorbar(mappable, ax=fig.axes, label="Unsigned distance (coordinate unit)", shrink=.7)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def render_report(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "result.json", result)
    rows = []
    if result.get("operation") == "convert":
        metrics = result.get("metrics", {})
        rows = [{"source_format": result.get("source_format"), "target_format": result.get("target_format"),
                 "export_status": result.get("export_status"), "readback_status": result.get("readback_status"),
                 "geometry_status": result.get("geometry_status"), "actual_representation": result.get("actual_representation"),
                 "d95_mm": metrics.get("d95"), "sampled_max_mm": metrics.get("sampled_max"),
                 "bbox_delta_mm": result.get("bbox_max_delta_mm"),
                 "convergence_delta_mm": result.get("convergence_delta_mm")}]
    elif "attempts" in result:
        for item in result["attempts"]:
            metrics = item.get("final_metrics", item.get("metrics", {}))
            rows.append({"candidate_id": item["candidate_id"], "parameters": json.dumps(item["parameters"], ensure_ascii=False),
                         "faces": item.get("actual_faces"), "status": item["status"], "decision": item["decision"],
                         "d95": metrics.get("d95"), "sampled_max": metrics.get("sampled_max"),
                         "area_change": metrics.get("area_change"), "volume_change": metrics.get("volume_change"),
                         "volume_status": metrics.get("volume_status"),
                         "reason_codes": ";".join(item["reason_codes"]), "error": item.get("error", "")})
    elif result.get("metrics"):
        m = result["metrics"]
        rows = [{k: m.get(k) for k in ("asd", "d95", "sampled_max", "area_change", "volume_change", "volume_status")}]
    if rows:
        with (directory / "results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    esc = lambda value: html.escape(str(value))
    table = ""
    if rows:
        table = "<div class='scroll'><table><thead><tr>" + "".join(f"<th>{esc(x)}</th>" for x in rows[0]) + "</tr></thead><tbody>"
        for row in rows:
            table += "<tr>" + "".join(f"<td>{esc(v) if v is not None else '不可用'}</td>" for v in row.values()) + "</tr>"
        table += "</tbody></table></div>"
    if rows and result.get("operation") == "convert":
        labels = ["输入格式", "输出格式", "文件写出", "目标回读", "几何检查", "实际表示", "D95 / mm",
                  "采样最大偏差 / mm", "包围盒最大差 / mm", "两档离散差 / mm"]
        table = "<table><tr><th>检查项目</th><th>本次结果</th></tr>" + "".join(
            f"<tr><td>{esc(label)}</td><td>{esc(value) if value is not None else '未执行'}</td></tr>"
            for label, value in zip(labels, rows[0].values())) + "</table>"
    figure = directory / "error.png"
    image = '<img src="error.png" width="780" alt="双向表面距离，固定相同色标">' if figure.exists() else ""
    scope = ("本报告只判定转换文件写出、独立回读及有限采样几何一致性。CAD源以细离散近似为参考，距离统一为mm；"
             "通过不代表完整医学资格、参数化历史恢复、有效实体或其他CAD软件兼容性。"
             if result.get("operation") == "convert" else
             f"输入版本：{esc(result.get('input_version', '未提供'))}。未提供成员1完整复检时，不认定优化正式合格；"
             "体积未获闭合、方向、自交及实体归属验证时记为不可用。未执行步骤保留为未执行。")
    body = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>医学网格处理报告</title>
<style>body{{font:15px/1.7 -apple-system,sans-serif;max-width:1150px;margin:40px auto;padding:0 24px;color:#22303d}}
h1,h2{{color:#172633}}.status{{padding:12px;background:#edf4f7}}table{{border-collapse:collapse;font-size:12px}}
th,td{{border:1px solid #d4dce0;padding:8px;text-align:left;white-space:nowrap}}th{{background:#eaf0f3}}
.scroll{{overflow:auto}}pre{{background:#f4f6f8;padding:16px;overflow:auto}}img{{max-width:100%}}</style>
<h1>医学三维网格处理报告</h1><p>成员2实验工作台 · 所有距离均为有限采样估计。</p>
<p class="status">执行：{esc(result.get('status'))}　判定：{esc(result.get('decision', 'not_applicable'))}　
质量：{esc(result.get('quality_status', 'unverified'))}</p>
<p>{scope}</p>
<h2>结果明细</h2>{table}{image}<h2>完整记录</h2><pre>{esc(json.dumps(result, ensure_ascii=False, indent=2))}</pre></html>"""
    (directory / "report.html").write_text(body, encoding="utf-8")
    return directory / "report.html"
