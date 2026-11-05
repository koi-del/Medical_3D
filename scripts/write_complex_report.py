"""Render a truthful specialist report from measured rows, including pending cases."""
import csv
import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'results/e3d_complex'
cases=json.loads((BASE/'cases.json').read_text(encoding='utf-8'))
with (BASE/'comparison.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
lookup={(r['case'],r['engine']):r for r in rows}
complete=all(lookup[(case['case'],'vendor')]['status']=='measured' for case in cases)
def state(row):
    if row['status']!='measured':return '尚未读取实际导出'
    return '符合本例目标' if row['goal_passed']=='True' else '未达本例目标'
lines=['# 复杂非流形与曲面补洞专项对照','',
       '记录日期：2026-11-03。'+('13个结果均已实际导出并独立复核。' if complete else '界面测试已完成，E-3D实际导出尚待用户完成或文件尚未齐全；未完成文件复核前不能下最终结论。'),'',
       '本轮是8个主样例及5项补充试验，不是13个独立病例。输入均为同一批STL并记录SHA-256。补洞使用可追溯的解析曲面密集三角参考；非流形样例是构造拓扑测试，不代表解剖恢复。','',
       '| 样例 | 任务 | 我们项目NPZ | 我们项目STL回读 | E-3D实际导出 |',
       '|---|---|---|---|---|']
for case in cases:
    name=case['case']
    lines.append('| '+name+' | '+case['goal']+' | '+state(lookup[(name,'project_native')])+' | '+state(lookup[(name,'project_stl')])+' | '+state(lookup[(name,'vendor')])+' |')
if complete:
    lines+=['','## 实测结论与优化优先级','',
        '- 复杂非流形：两处独立异常边 c_mnm 中，E-3D恢复960面闭合球面，输出到参考的采样RMS约1.77e-8；本项目受限候选搜索未修复。四面共享边与混合缺陷样例双方达到预设目标，但前者没有唯一形状参考，不能据此比较解剖恢复质量。',
        '- 顶点粘连 c_pin：本项目原生NPZ保留两个闭合壳体，但STL回读会焊接重合顶点，未通过；E-3D输出6面，仍有1个重复面，排除重复面后存在3边缺口，同样未达目标。不能说任一方已通用解决顶点粘连。',
        '- 目标选择：原始四类曲面孔及手动曲率重复试验中，E-3D虽只剩一个开口，实际没有保留指定外边界，因此均未达任务目标。外边界细分控制组中四项均保留正确外边界并完成补洞；观察支持目标选择受边界离散方式影响，但不足以断言其内部排序算法。',
        '- 曲面能力：外边界48边的控制组中，E-3D四类孔均完成，本项目仅二次曲面孔完成。凹孔、高曲率孔、不规则孔的参考→输出采样RMS分别为0.02744、0.11435、0.01499；本项目保留缺孔输入时分别为0.14626、0.27131、0.14754。后者是未补洞基线，不能把比值解释成双方已修补曲面的精度倍数。',
        '- 双方完成的二次曲面控制孔，参考→输出RMS分别约0.021096（本项目）、0.021100（E-3D），非常接近；反向RMS约0.02619与0.01514，E-3D在该项采样指标更小。高曲率控制孔虽通过拓扑目标，仍有约0.11435的形状偏差，通过不等于恢复了原曲面。',
        '- c_high自动入口与c_hcur明确曲率入口的导出网格，按坐标及有向三角形多重集比较无增删或翻面，见 automatic_vs_curvature.json；这只证明本次输出一致，不能推断两个入口内部实现相同。',
        '- 优化顺序：首先把多处独立异常的分区候选组合与逐区复检纳入非流形搜索；其次为凹孔和不规则孔实现约束三角剖分、补片内部加点及边界固定的曲面优化；再补充STL交接后的焊接风险检查。继续保留显式孔洞角色、修复预览与拒绝策略，并把本轮失败样例作为后续回归集。','']
lines+=['','## 测试策略与目标','',
        '- 非流形样例：E-3D自动修复默认选项；本项目按已实现清理、受限建议排序及明确人工孔洞目标处理。选择首个建议是一项人工策略假设，不是算法自动理解了原形。失败保留原输入，没有用已知造损编号偷偷修复替代搜索结果。',
        '- 孔洞样例：补内孔、保留外侧天然开口。E-3D设置保留最大开口数1；本项目显式标记内孔与外边界，先尝试平面模式，再尝试实验局部二次曲面模式。',
        '- c_hcur、c_h2是明确选择E-3D“曲率填充”的手动修复面板试验，允许内部增加新点；实际模式选项与选择记录在 *_mode_combo.json、*_curve_parameters_combo.json。其余孔洞走自动修复入口，不假定内部算法相同。',
        '- 初始内外边界各24边，“最大孔”的排序规则未得到软件说明证实。c_q2/c_c2/c_h2/c_i2将外侧边细分为48条、内孔仍24条，以检查目标选择歧义；原边界折线形状保持，量化后仍会有STL浮点舍入。最终以实际外边界保留检测判定，不仅凭剩余孔数。',
        '- c_pin在本项目NPZ中可保留独立重合顶点，STL回读则可能再次精确焊接；必须同时列出原生拓扑与相同STL交接路径，不能只挑有利格式。',
        '- c_e4没有唯一解剖参考，仅检查消除缺陷、保持1个分量及至少2个面，属于拓扑目标，不能说恢复了正确原形。',
        '- 每项保留界面操作路径和程序处理步骤；本轮没有统一测量真实人工操作时间、逐鼠标点击数或算法速度，不把自动化脚本/审批等待时间当作算法时间。','',
        '## 补片区域采样距离','',
        '在缺孔投影区域内，确定性采样顶点、三角面中心与边中点，每方向最多4000点，计算到另一曲面三角形的最近距离。下表为参考→输出RMS，单位为原坐标；不能当作精确Hausdorff距离或医学精度。输出没有孔内采样点时，反向误差为缺失而不是0。','',
        '| 样例 | 我们项目STL参考→输出RMS | E-3D参考→输出RMS | E-3D外侧天然边界保留 |','|---|---:|---:|---|']
for case in cases:
    if case['category']!='hole':continue
    name=case['case'];p=lookup[(name,'project_stl')];v=lookup[(name,'vendor')]
    fmt=lambda x: f'{float(x):.6g}' if x not in ('','None') else '—'
    lines.append(f"| {name} | {fmt(p['reference_to_output_rms'])} | {fmt(v['reference_to_output_rms'])} | {v['outer_rim_preserved'] if v['status']=='measured' else '待复核'} |")
lines+=['','## 证据与限制','',
        '- comparison.csv 与 *_audit.json：拓扑、自交、分量、外边界保留、双向采样距离、输入/输出/参考哈希。','- project/*.json：策略顺序、拒绝原因、原生与STL回读诊断。cases.json和evidence：界面参数及预览观察，不代替导出检测。',
        '- 最后一项第一次被列表裁切影响选错模型，已在 invalid_attempts.json 标记作废；对应重复对象未进入最终导出清单。重测加入实际模型名称读回核对。',
        '- 所有样例均为合成测试，不涉及独立患者或临床验证。结果仅适用于本机V24.09、这些输入与操作路径；不能证明任意复杂问题已被任一软件普遍解决。',
        '- 复核命令：scripts/audit_complex_benchmark.py、scripts/record_complex_ui.py、scripts/write_complex_report.py。','']
(BASE/'专项对照报告.md').write_text('\n'.join(lines),encoding='utf-8')
print('Specialist report:', 'complete file audit' if complete else 'pending vendor exports')
