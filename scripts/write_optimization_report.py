"""Measured comparison and workflow improvements, with explicit comparison limits."""
import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'results/e3d_optimization'
rows=list(csv.DictReader((base/'comparison.csv').open(encoding='utf-8-sig')));lookup={(r['case'],r['engine']):r for r in rows}
complete=all(lookup[(n,'vendor')]['status']=='measured' for n in ('o_s50','o_s20','o_k20','o_closed','o_open','o_remesh'))
names={'o_s50':'球面保留50%','o_s20':'球面保留20%','o_k20':'图谱右肾保留20%','o_closed':'闭合噪声球面平滑','o_open':'开放噪声曲面平滑','o_remesh':'球面重划分'}
lines=['# 网格优化专项对照与统一工作流程','',
       '日期：2026-11-04。'+('6个E-3D实际导出STL均已独立回读复核。' if complete else '仍有E-3D导出缺失，未完成全部文件对照。'),'',
       '这是6项固定输入试验，含重复球面及一个公开BodyParts3D图谱右肾，不是独立患者样本。所有输入记录SHA-256；优化前实现保存在 baseline_filters.py。实际参数与去除账号栏的证据在 ui_trials.json、evidence。','',
       '## 相同输入的实测结果','',
       '每方向50,000个面积加权样本，固定种子，计算点到三角表面的距离；D95取双向95分位较大值。距离均为原坐标单位，不能跨样例比较物理精度；未知单位不换算毫米。最大采样偏差不是精确Hausdorff。','',
       '| 样例 | 项目输出面数 | E-3D面数 | 项目D95（对输入） | E-3D D95（对输入） | 项目结构复核 | E-3D结构复核 |',
       '|---|---:|---:|---:|---:|---|---|']
for name,label in names.items():
    p=lookup[(name,'project_after')];v=lookup[(name,'vendor')]
    fmt=lambda r,k:f'{float(r[k]):.6g}' if r.get(k) else '—'
    lines.append(f"| {label} | {p.get('faces','—')} | {v.get('faces','—')} | {fmt(p,'d95')} | {fmt(v,'d95')} | {p.get('structure','未测')} | {v.get('structure','未测')} |")
lines+=['','## 能得出的结论','',
    '- 三项简化的实际输出面数分别一致（480、192、2478）。在本轮输入及参数下，项目对输入的D95、面积/体积变化和低分位三角形质量优于E-3D结果；不代表对所有器官或不同配置都成立。E-3D使用“输出高质量网格单元”开启、保留比例0.5/0.2；其内部简化算法未得到独立确认。',
    '- 平滑需区分保留输入与恢复干净参考。E-3D开放曲面的输入偏差更小；项目对已知干净参考的偏差更小。E-3D使用5次、特征角70°、强度0.1、保持边界；项目使用5次Taubin，两者不是同一个算法或等价强度。本轮仅比较这两个明确配置。',
    '- 重划分按相同目标边长3、3次原始迭代比较，实际面数不同（项目728、E-3D 682），所以不是等面数或等耗时比赛。项目新增最多3轮带表面投影的质量增强，执行参数及采样保护在算法记录中；质量提升的计算成本应单独考虑。','',
    '## 去噪参考与重划分质量','',
    '| 噪声样例 | 噪声输入→干净参考D95 | 项目输出→干净参考D95 | E-3D输出→干净参考D95 |','|---|---:|---:|---:|']
for name in ('o_closed','o_open'):
    p=lookup[(name,'project_after')];v=lookup[(name,'vendor')]
    lines.append(f"| {names[name]} | {float(p['input_clean_reference_d95']):.6g} | {float(p['clean_reference_d95']):.6g} | {float(v['clean_reference_d95']):.6g} |")
lines+=['','上表仍是双向D95（参考→结果及结果→参考的较大分位），不是单方向距离。干净参考只用于这两项已知造噪试验，不把未知原始解剖曲面当成已知。','',
    '| 重划分指标 | 原项目 | 优化后项目 | E-3D |','|---|---:|---:|---:|']
data=[lookup[('o_remesh',e)] for e in ('project_before','project_after','vendor')]
lines.append('| 三角形质量5%分位（越高越好） | '+' | '.join(f"{json.loads(r['quality'])['q_p5']:.6g}" for r in data)+' |')
lines.append('| D95（越低越好） | '+' | '.join(f"{float(r['d95']):.6g}" for r in data)+' |')
lines+=['','三角形质量q=4√3×面积/三边长度平方和，等边为1、退化为0。质量增强后项目仍未在该低分位质量指标上超过E-3D，保留这个差距。低偏差、均匀三角形和减少面数之间存在取舍。','',
    '## 已落地的改进','',
    '- 简化支持百分比和目标面数两种输入，显示预计面数；QEM明确启用法线、边界、拓扑保护及质量阈值。球面50%样例D95从约0.11115降至0.10262；另外两项未观察到改变，不把未变化写成提升。',
    '- 重划分质量增强使用切向松弛和原表面投影，只接受低分位质量提高且2000点保护采样未明显增加偏差的步骤；正式候选仍需独立至少50,000点及拓扑/自交复核。',
    '- 用户选择未最终复核的其他候选时，对原候选补做独立最终复核，不重新生成另一个版本；复核通过后才进入共享预览。',
    '- 误差色图默认绘制在模型表面，每面颜色是该面样本均值；灰色为未采样，保留实体颜色和原始采样点切换。统计继续使用原始距离数组。',
    '- 只有拓扑、自交、方向和单闭合壳体验证通过时才报告围合体积及变化；开放面、多壳体或未验证模型的体积仍为空。',
    '- 统一界面按“检查修复→简化平滑→误差对比→格式导出”组织，不再按成员/任务划分。顶部打开/检查/回退/历史/保存、中央画布、左侧参数、右侧结果报告、底部预览接受放弃和取消保持固定位置。参数按操作显示，高级阈值折叠；未接受结果不替换当前模型。','',
    '## 格式转换对照范围','',
    '本次实际读取的E-3D网格导出格式为STL、OBJ、PLY；CAD建模工具栏另有实体、布尔等工具，未找到与项目STEP/IGS六向写出/独立回读完全对应且可执行的入口。因此不声称E-3D没有CAD能力，也不编造其STEP/IGS对照结果。后续本机已配置便携FreeCAD并完成24/24六向转换、8/8异常及单位验证，六方向桌面操作通过、完整回归145项通过且无跳过。详细证据及E-3D比较边界见[六向专项报告](../cad_six_directions/专项验证报告.md)。网格优化对照已完成，E-3D六向数值对照仍不可执行。','',
    '## 验证、限制与复现','',
    '- 所有结果均为实际文件。comparison.csv及逐例审计JSON含输入输出哈希、50,000点距离、质量、体积条件、拓扑、自交和边界对应；reference_eligible并不代表临床合格。',
    '- 本轮没有统一测量E-3D算法耗时或人工操作时间，不能据此比较效率。无多病例盲测；开发集上的优化不能解释为普遍超越。',
    '- 复现：scripts/prepare_optimization_benchmark.py（只允许首次生成输入）、scripts/audit_optimization_benchmark.py、scripts/write_optimization_report.py。实际界面验证见 results/workflow_ui_verification/verification.json，脚本scripts/verify_workflow_window.py。','']
(base/'优化对照与统一流程报告.md').write_text('\n'.join(lines),encoding='utf-8');print('Report complete:',complete)
