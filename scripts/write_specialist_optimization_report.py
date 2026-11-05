"""Publish the new run separately from frozen vendor and pre-optimization audits."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'results/specialist_optimization'
with (out/'comparison.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
lookup={r['case']:r for r in rows}
yes=lambda value:'通过' if value=='True' else '未通过'
lines=['# 专项对照后的算法优化与验证','',
       '日期：2026-11-04。本次保留原始E-3D导出及优化前项目结果，另存本轮结果，未重新操作E-3D或产生导出费用。','',
       '## 实现与使用','',
       '- 多处非流形：将共享异常面的边划入邻域，以有界束搜索组合不同邻域的删面方案，再对每个候选执行整模拓扑、自交、分量和受保护开口复检。最多组合8个邻域、每条异常边最多6个关联面、整模最多50000面，候选复检仍受1—48预算约束。排序与建议均不自动提交。',
       '- 曲面补洞：新增“邻域曲面补片（实验，支持凹孔与内部加点）”。使用两环邻域、投影稳定性筛选、带二次多项式约束的薄板插值、保留孔边的耳切三角化、内部边细分和质量改进。全部原顶点与原面保留，仅在目标孔内加入补片；细分目标随最长固定孔边调整，避免不规则采样下无止境加点。',
       '- 新模式仍限6—64边简单高度场孔、256个邻域点、768个内部新点，跨度上限沿用界面设置。保持天然开口、连通分量保护，强制自交复检；不满足条件时拒绝并保留输入。不是任意拓扑、任意解剖曲面的通用重建。',
       '- STL实际回读：每次保存后重新读取实际文件，比较拓扑指标；结果与文件SHA-256写入 .stl.json 的 export_validation，GUI打印风险提示。导出检查仅验证拓扑，自交状态明确记录为 unverified；不移动重合顶点来掩盖格式限制。',
       '- 补齐质量优化：固定所有原顶点，仅调整补片新顶点在投影内的位置，再映射回拟合曲面；逐次检查不翻转、局部最小三角形角度提高。最终仍执行整模自交复检。操作记录保存优化前后最小角及移动次数。',
       '- 补齐交接方案：新增“分壳STL集合 (*.stlset.zip)”及公共接口 save_shell_set(asset,path)。每个壳体独立导出、实际回读并复检拓扑和自交；二进制舍入破坏拓扑时尝试ASCII，仍失败则拒绝生成集合。ZIP保存逐壳源面索引、文件哈希和复检结果。必须将各文件作为独立对象导入；合并焊接仍会重新粘连。',
       '- 操作：重启启动脚本；导入后把目标孔标为“修复目标”，把应保留的开口标为“天然开口”；在补洞方法下拉框选新增邻域曲面模式，生成预览，检查后接受。非流形沿用“生成修复建议→选择方案→生成预览→接受”的流程。','',
       '## 同输入STL回归','',
       '沿用13项试验（8主样例与5项相关补充），按原输入哈希核对。表中“通过”是预定拓扑、开口和结构目标，不代表临床精度。','',
       '| 样例 | 优化前STL | 优化后NPZ | 优化后STL | 原E-3D导出 |','|---|---|---|---|---|']
for row in rows:
    lines.append('| '+row['case']+' | '+' | '.join(yes(row[k]) for k in ('before_pass','optimized_native_pass','optimized_stl_pass','vendor_pass'))+' |')
lines+=['','## 双方均保留正确开口的曲面控制组','',
        '下表为原对照方法的参考→输出三角曲面距离采样RMS，使用相同参考样点，单位为原坐标；越小越接近该参考。仅比较双方均完成任务的控制组，不能推广为患者准确率或总体能力倍数。','',
        '| 孔洞 | 优化后项目RMS | E-3D RMS |','|---|---:|---:|']
for name,label in [('c_q2','二次曲面'),('c_c2','凹孔'),('c_h2','高曲率'),('c_i2','不规则采样')]:
    row=lookup[name]
    lines.append(f"| {label} | {float(row['optimized_rms']):.6g} | {float(row['vendor_rms']):.6g} |")
lines+=['','## 补片角度优化实测','',
        '| 控制样例 | 优化前最小角 | 优化后最小角 |','|---|---:|---:|']
for name in ('c_q2','c_c2','c_h2','c_i2'):
    record=json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
    op=record['steps'][0]['operations'][-1]
    lines.append(f"| {name} | {op['minimum_angle_before_degrees']:.2f}° | {op['minimum_angle_after_degrees']:.2f}° |")
lines+=['','## 完成范围与仍存在的限制','',
        '- 本轮优化清单已落实：多处非流形组合建议、复杂曲面补片、补片角度改善、STL回读检查、分壳交接、界面预览与审核、测试和交付资料。这里的完成指这些明确功能，不代表所有医学三维修复问题均已解决。',
        '- 验证：92项自动测试通过；实际Qt/VTK窗口验证结果见 ../specialist_ui_verification/verification.json，包含新增模式、QProcess后台补洞、审核提交和真实导出分支；高曲率补片截图为 high_curvature_preview.png。',
        '- c_pin原生NPZ可保留两个闭合壳体；单个STL精确焊接回读仍使拓扑失效。新增分壳集合提供两个分别验证闭合的STL交接方案，不能把集合成功等同于单文件已消除表达限制。',
        '- 部分曲面和网格质量选择使用了本轮失败样例做回归，因此这些是开发集改善结果，不是独立盲测。另加18边、27边的旋转平移缩放凹孔，以及打乱面序的三处非流形测试，检查对面编号和坐标方向的依赖，但这些仍为合成样例。',
        '- 新曲面模式可能生成比E-3D更多的三角形，本次没有做等三角形预算或统一速度对照，不把距离优势解释为计算效率优势。高曲率误差仍不为零，未知原形不能仅由孔边唯一确定。',
        '- 多处非流形仍是有界搜索，复杂相互耦合的异常邻域可能无建议。候选必须人工审核。',
        '- 原始对照与界面证据见 ../e3d_complex/专项对照报告.md；本轮 comparison.csv、逐例JSON记录实际修复步骤、拒绝信息、原生及STL复检与双向误差。复现命令：scripts/verify_specialist_optimization.py、scripts/write_specialist_optimization_report.py。','']
(out/'优化验证报告.md').write_text('\n'.join(lines),encoding='utf-8')
print(out/'优化验证报告.md')
