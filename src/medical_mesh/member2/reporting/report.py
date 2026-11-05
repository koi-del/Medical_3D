import csv
import html
import json
from pathlib import Path
import numpy as np
from medical_mesh.member2.core.model import write_json
from medical_mesh.ui.feedback import explain_reasons,REASONS


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
    labels_map={'candidate_id':'方案','parameters':'处理参数','faces':'三角面数','status':'执行状态','decision':'判定','d95':'D95','sampled_max':'采样最大偏差','area_change':'面积变化比例','volume_change':'围合体积变化比例','volume_status':'体积验证','reason_codes':'未通过原因','error':'错误','asd':'双向平均偏差'}
    statuses={'completed':'计算完成','failed':'失败','accepted':'复核通过（仍需人工接受）','rejected':'未通过','unverified':'未验证','not_applicable':'不适用','passed':'通过','verified':'已验证','not_run':'未执行','timeout':'超时','cancelled':'已取消','qem':'QEM简化','laplacian':'Laplacian平滑','taubin':'Taubin平滑','remesh':'均匀重划分','surface':'面片曲面'}
    statuses['unavailable']='不可用'
    def readable(value):
        if value is None:return '不可用'
        if isinstance(value,float):return f'{value:.7g}'
        if isinstance(value,str):
            if any(part in REASONS for part in value.split(';')):return explain_reasons(value.split(';'))
            if value.startswith('{'):
                try:
                    names={'operation':'方法','keep_ratio':'保留比例','iterations':'迭代次数','target_edge_length':'目标边长','target_faces':'目标面数','smooth_iterations':'Taubin平滑次数','quality_refinement':'质量增强'}
                    return '；'.join(f'{names.get(k,k)}：{statuses.get(str(v),v)}' for k,v in json.loads(value).items())
                except (ValueError,AttributeError):pass
            return statuses.get(value,value)
        return str(value)
    esc = lambda value: html.escape(readable(value))
    table = ""
    if rows:
        table = "<div class='scroll'><table><thead><tr>" + "".join(f"<th>{esc(labels_map.get(x,x))}</th>" for x in rows[0]) + "</tr></thead><tbody>"
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
             f"距离单位：{esc(result.get('metrics',{}).get('coordinate_unit','见各方案记录'))}。未完成完整结构复检时，不认定模型修复合格；"
             "体积未获闭合、方向、自交及实体归属验证时记为不可用。未执行步骤保留为未执行。")
    if result.get('operation')=='evaluate':scope+=' 本任务只评价表面距离；质量未验证表示没有执行完整结构资格检查，不表示距离计算失败。'
    topology=''
    if result.get('diagnosis_before') and result.get('diagnosis_after'):
        names={'vertex_count':'顶点数','face_count':'三角面数','duplicate_face_count':'重复面','degenerate_face_count':'退化面','boundary_loop_count':'边界环','component_count':'连通分量','non_manifold_edge_count':'非流形边','non_manifold_vertex_count':'非流形顶点','orientation_conflict_count':'方向冲突边'}
        before=result['diagnosis_before']['metrics'];after=result['diagnosis_after']['metrics']
        topology='<h2>处理前后结构检查</h2><table><tr><th>检查项</th><th>处理前</th><th>处理后预览</th></tr>'+''.join(f'<tr><td>{label}</td><td>{esc(before.get(key))}</td><td>{esc(after.get(key))}</td></tr>' for key,label in names.items())+'</table>'
    issues=result.get('errors',[])+result.get('warnings',[])+result.get('reason_codes',[])
    explanation='<p>'+esc(explain_reasons(issues) if issues else '本次没有记录执行错误。请结合结构检查、误差门槛及人工预览判断结果。')+'</p>'
    criteria=''
    limits=result.get('limits',{})
    if limits:
        criteria='<h2>本次验收门槛</h2><p>D95/包围盒对角线 ≤ '+esc(limits.get('d95_normalized'))+'；采样最大偏差/对角线 ≤ '+esc(limits.get('sampled_max_normalized'))+'；面积相对变化 ≤ '+esc(limits.get('area_change'))+'。例如0.1为对角线10%，面积0.5为50%，均属于宽松的流程测试范围，不能用来证明高精度。</p>'
        criteria+='<table><tr><th>方案</th><th>D95/对角线实测</th><th>最大偏差/对角线实测</th><th>面积变化实测</th><th>拒绝原因</th></tr>'
        for item in result.get('attempts',[]):
            m=item.get('final_metrics',item.get('metrics',{}))
            criteria+='<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (item.get('candidate_id'),m.get('d95_normalized'),m.get('sampled_max_normalized'),m.get('area_change'),explain_reasons(item.get('reason_codes',[])) or '无拒绝原因'))+'</tr>'
        criteria+='</table>'
    operation={'repair':'网格修复','diagnose':'网格检测','load':'模型导入与检测','optimize':'简化、平滑或重划分','verify_candidate':'候选独立复核','evaluate':'双向表面误差评价','convert':'CAD格式转换'}.get(result.get('operation'),'网格处理')
    input_name=result.get('input_path','')
    request_file=directory/'request.json'
    if request_file.exists():
        try:input_name=json.loads(request_file.read_text(encoding='utf-8')).get('input_path',input_name)
        except ValueError:pass
    body = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>医学网格处理报告</title>
<style>body{{font:15px/1.7 -apple-system,sans-serif;max-width:1150px;margin:40px auto;padding:0 24px;color:#22303d}}
h1,h2{{color:#172633}}.status{{padding:12px;background:#edf4f7}}table{{border-collapse:collapse;font-size:12px}}
th,td{{border:1px solid #d4dce0;padding:8px;text-align:left}}th{{background:#eaf0f3}}
.scroll{{overflow:auto}}pre{{background:#f4f6f8;padding:16px;overflow:auto}}img{{max-width:100%}}</style>
<h1>医学三维模型处理与质量评价报告</h1><p>任务：{esc(operation)} · 本报告仅说明本次处理及验证范围。</p>
<p>输入：{esc(input_name or '见任务输入记录')}<br>输入版本：{esc(result.get('input_version','未提供'))}<br>任务编号：{esc(result.get('run_id',directory.name))}<br>计算用时：{esc(result.get('elapsed_seconds'))} 秒</p>
<p class="status">执行：{esc(result.get('status'))}　判定：{esc(result.get('decision', 'not_applicable'))}　
质量：{esc(result.get('quality_status', 'unverified'))}</p>
<p>{scope}</p><p>人工审核：{esc({'accepted':'已接受并更新正式版本','discarded':'已放弃，原版本保持'}.get(result.get('user_review'),'待人工审核' if result.get('diagnosis_after') else '本任务未提交模型变更'))}</p>
{topology}<h2>结果明细</h2>{table}{criteria}{image}<h2>判定说明与后续操作</h2>{explanation}
<h2>指标释义</h2><p>ASD为双向平均表面距离；D95为双向采样距离的95百分位；采样最大偏差仅为本次样本中最大值，不是严格Hausdorff上界。面积及围合体积变化为相对变化比例；未知单位不解释为毫米。两侧误差图采用相同色标，灰色面表示未采样。</p>
<h2>结果使用范围</h2><p>计算完成、结构通过、几何阈值通过与用户接受是不同状态。待接受预览不会自动替换正式版本；独立评价和格式转换也不会替换正式网格。临床有效性、通用曲面重建和第三方软件兼容性不能由本报告单独认定。原始审计数据另外保存在任务目录中。</p></html>"""
    (directory / "report.html").write_text(body, encoding="utf-8")
    return directory / "report.html"
