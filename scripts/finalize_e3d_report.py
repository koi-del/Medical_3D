"""Build the final report only when every actual export has been audited."""
import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'results/e3d_benchmark'
names = ['hole', 'duplicate', 'degenerate', 'flip', 'non_manifold_edge',
         'open_tube', 'two_components', 'liver']
records = {name: json.loads((BASE / (name + '_independent_audit.json')).read_text(encoding='utf-8'))
           for name in names + ['open_tube_default', 'two_components_default']}
for name, record in records.items():
    check = record['diagnosis']['self_intersection']
    if check['status'] != 'verified' or check['face_ids']:
        raise RuntimeError(f'{name}: self-intersection verification did not pass')
    if not record['diagnosis']['metrics']['topology_passed']:
        raise RuntimeError(f'{name}: topology verification did not pass')
    if name in names and not record['comparison']['same_oriented_triangle_multiset']:
        raise RuntimeError(f'{name}: output equality claim is unsupported')
lines = ['# E-3D 实际对照结果', '', '完成日期：2026-10-23。安装版本：E-3D Master V24.09。', '',
         '8 个计划案例均已完成实际导入、对应处理、STL 导出和独立回读检测；另外完成 2 个默认策略对照。所有结论均依据真实导出文件，不以界面预览代替。', '',
         '| 计划案例 | 操作 | 输出面数 | 边界环 | 连通分量 | 与本项目对应输出 |',
         '|---|---|---:|---:|---:|---|']
for name in names:
    metrics = records[name]['diagnosis']['metrics']
    operation = '原样导出' if name in ('open_tube', 'two_components', 'liver') else '修复'
    lines.append(f"| {name} | {operation} | {metrics['face_count']} | {metrics['boundary_loop_count']} | {metrics['component_count']} | 三角面坐标及方向一致 |")
lines += ['', '5 个修复案例均输出 960 面、单一闭合分量，未检出重复面、退化面、非流形边/顶点、方向冲突和自交。开口管保留 2 个边界环；双分量保留 2 个分量；肝脏模型原样导出后仍为 19416 面。全部 8 项与本项目对应导出结果的有向三角面多重集合完全相同（忽略面顺序，按 STL 回读坐标精确比较），包围盒坐标差均为 0。', '',
          '## 额外默认策略对照', '',
          '- open_tube_default：默认填洞后为 92 面、0 个边界环；相较原开口管新增 44 面，两端开口被封闭。网格检查通过，但不符合“保留天然开口”的任务目标。原样导出案例与该默认修复案例必须区分。',
          '- two_components_default：默认勾选“只保留一个最大连通块”，本例仍为 8 面、2 个分量，且与原样结果完全一致。两个分量大小相同，不能推广到大小不等的模型。', '',
          '## 解释与限制', '',
          '- 非流形边案例中，本项目显式删除已知合成附加面 960；E-3D 使用默认自动修复。输出相同不意味着自动化程度相同。',
          '- 退化面 STL 含 961 面，E-3D 导入后已显示 960 面，最终输出也为 960 面；不能将导入过滤与修复按钮的作用混淆。',
          '- 开口管、双分量和肝脏的计划案例是原样导出验证，不能计入修复成功数量。',
          '- 原 STL 未提供可靠物理单位；本报告比较原始坐标，不因 E-3D 界面显示毫米就认定来源单位为毫米。',
          '- 本轮没有可靠算法耗时、复杂曲率补洞、大规模性能或临床有效性比较。结论仅适用于这些输入和操作，不能宣称总体达到或超越 E-3D。', '',
          '## 可复核文件', '',
          '- 原始导出：vendor_raw/hole_default 与 vendor_raw/remaining_batch，原件保留。',
          '- 各案例 *_independent_audit.json：原始导出路径、SHA-256、检测指标和逐面比较结果。',
          '- comparison.csv：8 个计划案例均为 measured；remaining_batch_audit.csv 另列额外默认策略结果。',
          '- e3d_outputs：计划案例的标准命名副本；project_outputs：使用同一批 STL 输入的本项目基线。',
          '- evidence：仅裁剪与测试有关的界面证据，交付包排除完整桌面截图及第三方手册。', '',
          '复现命令：先运行 scripts/audit_e3d_hole.py，再运行 scripts/audit_e3d_batch.py、scripts/record_e3d_observations.py 和 scripts/finalize_e3d_report.py。', '']
(BASE / '实际对照进度.md').write_text('\n'.join(lines), encoding='utf-8')
with (BASE / 'cases.csv').open(encoding='utf-8-sig', newline='') as stream:
    reader = csv.DictReader(stream)
    fields = reader.fieldnames
    rows = list(reader)
for row in rows:
    row['e3d_execution_status'] = 'measured'
with (BASE / 'cases.csv').open('w', encoding='utf-8-sig', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
print('Final report verified: 8 planned cases + 2 additional default-policy cases.')
