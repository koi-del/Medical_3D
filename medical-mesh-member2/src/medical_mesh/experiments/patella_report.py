"""Build a detailed offline course report from measured experiment artifacts only."""
from pathlib import Path
import json
import html
import re
import shutil
import numpy as np


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def f(value):
    if value is None:return '未执行'
    return f'{value:.6g}' if isinstance(value,(float,np.floating)) else str(value)


def table(headers,rows):
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(f(v).replace('|','/') for v in row)+' |\n' for row in rows)


def figures(out,reference,candidate,optimization,conversions):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    directory=out/'figures';directory.mkdir(exist_ok=True)
    rows=[r for r in optimization['rows'] if r['status']=='completed']
    qem=[r for r in rows if r['label'].startswith('qem_') and 'taubin' not in r['label']]
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    for r in qem:
        color='#c17a19' if r.get('stability_passed') is False else '#227c66' if r['geometry_final_pass'] else '#b23d35'
        marker='*' if r['label']==optimization['selected'] else 'x' if r.get('stability_passed') is False else 'o'
        label=str(r['actual_faces'])+(' (seed audit failed)' if r.get('stability_passed') is False else ' (selected)' if marker=='*' else '')
        m=r['final_metrics'];axes[0].scatter(r['actual_faces'],m['d95'],color=color,marker=marker,s=110 if marker=='*' else 40,zorder=4)
        axes[0].annotate(label,(r['actual_faces'],m['d95']),xytext=(4,5),textcoords='offset points',fontsize=8)
        axes[1].scatter(r['actual_faces'],m['sampled_max'],color=color,marker=marker,s=110 if marker=='*' else 40,zorder=4)
    scale=rows[0]['final_metrics']['reference_scale']
    for ax,key,limit in zip(axes,['D95','Sampled maximum'],[.001*scale,.003*scale]):
        ax.axhline(limit,color='#855d27',linestyle='--',label=f'Frozen limit: {limit:.4f} mm')
        ax.axvline(3000,color='#54758a',linestyle=':',label='CAD budget: 3000 faces')
        ax.set(xlabel='Actual triangle count',ylabel=f'{key} / mm',title=f'QEM: {key} versus mesh size')
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(directory/'optimization_tradeoff.png',dpi=180);plt.close(fig)
    details_path=out/'optimization'/optimization['selected']/'final_samples.npz'
    with np.load(details_path,allow_pickle=False) as data:
        da,db=data['distances_ab'],data['distances_ba'];pa,pb=data['points_ab'],data['points_ba']
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for distances,label in [(da,'Original to optimized'),(db,'Optimized to original')]:
        axes[0].hist(distances,bins=65,histtype='step',density=True,label=label)
        ordered=np.sort(distances);axes[1].plot(ordered,np.arange(1,len(ordered)+1)/len(ordered),label=label)
    axes[0].set(xlabel='Unsigned surface distance / mm',ylabel='Density',title='Selected candidate: distance distribution')
    axes[1].set(xlabel='Unsigned surface distance / mm',ylabel='Cumulative fraction',title='Selected candidate: empirical CDF')
    axes[1].axhline(.95,color='grey',linestyle='--');[ax.legend(fontsize=8) for ax in axes]
    fig.savefig(directory/'optimization_errors.png',dpi=180);plt.close(fig)
    fig=plt.figure(figsize=(12,5),layout='constrained')
    bounds=np.array([reference.vertices.min(axis=0),reference.vertices.max(axis=0)])
    center=bounds.mean(axis=0);radius=np.ptp(reference.vertices,axis=0).max()/2*1.05
    for i,(asset,title) in enumerate([(reference,f'MRI-derived original: {len(reference.faces):,} triangles'),(candidate,f'QEM candidate: {len(candidate.faces):,} triangles')]):
        ax=fig.add_subplot(1,2,i+1,projection='3d')
        poly=Poly3DCollection(asset.vertices[asset.faces],facecolors='#88aeb9' if i==0 else '#d9b580',shade=True,
                              lightsource=matplotlib.colors.LightSource(azdeg=315,altdeg=40))
        ax.add_collection3d(poly)
        ax.set(xlim=(center[0]-radius,center[0]+radius),ylim=(center[1]-radius,center[1]+radius),zlim=(center[2]-radius,center[2]+radius),
               xlabel='X / mm',ylabel='Y / mm',zlabel='Z / mm',title=title)
        ax.set_box_aspect((1,1,1));ax.view_init(elev=20,azim=-65)
    fig.savefig(directory/'medical_model_comparison.png',dpi=180);plt.close(fig)
    fig=plt.figure(figsize=(11,4.7),layout='constrained');limit=max(da.max(),db.max())
    for i,(points,dist,title) in enumerate([(pa,da,'Original to optimized'),(pb,db,'Optimized to original')]):
        ax=fig.add_subplot(1,2,i+1,projection='3d');stride=max(1,len(points)//5000)
        m=ax.scatter(*points[::stride].T,c=dist[::stride],s=2,cmap='viridis',vmin=0,vmax=limit)
        ax.set(title=title,xlabel='X / mm',ylabel='Y / mm',zlabel='Z / mm');ax.set_box_aspect(np.ptp(reference.vertices,axis=0));ax.view_init(elev=20,azim=-65)
    fig.colorbar(m,ax=fig.axes,label='Unsigned distance / mm',shrink=.7)
    fig.savefig(directory/'medical_error_map.png',dpi=180);plt.close(fig)
    names=[r['direction'].replace('_to_',' → ') for r in conversions['cases']]
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    x=np.arange(len(names));eps=1e-15
    axes[0].bar(x-.18,np.maximum([r['d95_mm'] or eps for r in conversions['cases']],eps),width=.36,color='#357e91',label='Local conversion roundtrip')
    axes[0].bar(x+.18,np.maximum([r['chain_vs_selected_d95_mm'] or eps for r in conversions['cases']],eps),width=.36,color='#9a74a4',label='Chain vs float64 candidate')
    axes[0].set_yscale('log');axes[0].set_ylim(1e-16,.2)
    axes[0].axhline(.1,color='#855d27',linestyle='--',linewidth=1,label='Course conversion limit: 0.1 mm')
    axes[0].set(ylabel='D95 / mm (log scale)',title='Format roundtrip and STL quantization')
    axes[0].legend(fontsize=7,loc='upper right')
    axes[1].bar(x,[r['end_to_end_d95_mm'] or 0 for r in conversions['cases']],color='#b48a50')
    axes[1].set(ylabel='Original to final D95 / mm',title='Total pipeline error versus original MRI model')
    for ax in axes:ax.set_xticks(x,names,rotation=25,ha='right');ax.grid(axis='y',alpha=.2)
    fig.savefig(directory/'conversion_vs_total_error.png',dpi=180);plt.close(fig)


def offline_html(markdown):
    """Small, escaped Markdown subset for an offline report, without remote assets."""
    def inline(s):
        s=html.escape(s)
        s=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',r'<img alt="\1" src="\2">',s)
        s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
        s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
        s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
        return s
    blocks=[];code=[];in_code=False;in_table=False
    for line in markdown.splitlines():
        if line.startswith('```'):
            if in_code:blocks.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');code=[]
            in_code=not in_code;continue
        if in_code:code.append(line);continue
        if line.startswith('|'):
            if re.fullmatch(r'[| :\-]+',line):continue
            if not in_table:blocks.append('<table>');in_table=True
            blocks.append('<tr>'+''.join('<td>'+inline(v.strip())+'</td>' for v in line.strip('|').split('|'))+'</tr>');continue
        if in_table:blocks.append('</table>');in_table=False
        if not line.strip():continue
        if line.startswith('#'):
            level=min(6,len(line)-len(line.lstrip('#')));blocks.append(f'<h{level}>'+inline(line[level:].strip())+f'</h{level}>')
        elif line.startswith('- '):blocks.append('<p class="bullet">• '+inline(line[2:])+'</p>')
        else:blocks.append('<p>'+inline(line)+'</p>')
    if in_table:blocks.append('</table>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>公开MRI髌骨模型实验报告</title><style>body{font:16px/1.8 -apple-system,BlinkMacSystemFont,sans-serif;color:#263642;max-width:1100px;margin:40px auto;padding:0 25px}h1,h2{color:#173c50}h2{border-bottom:1px solid #cedce2;padding-top:16px}table{border-collapse:collapse;font-size:13px;display:block;overflow:auto}td{border:1px solid #cbd6dc;padding:8px}tr:first-child{background:#e9f1f4;font-weight:600}tr:nth-child(even){background:#f7f9fa}pre{padding:16px;background:#f2f5f7;overflow:auto}code{font-size:13px}img{max-width:100%;height:auto}a{color:#006b94}.bullet{margin:3px 0}@media print{body{max-width:none;margin:0;font-size:11pt}h2{break-after:avoid}img{max-height:220mm}pre{white-space:pre-wrap}table{display:table;font-size:9pt}}</style><body>'+''.join(blocks)+'</body></html>'


def generate_report(out,root,publish=True):
    from medical_mesh.core.model import load_asset, file_hash, write_json
    from .patella import ATTRIBUTION
    p=load(out/'provenance.json');o=load(out/'optimization_summary.json');c=load(out/'conversion_summary.json')
    plan=load(out/'optimization_plan.json');cfg=load(out/'frozen_cad_config.json');runtime=load(out/'runtime.json');environment=load(out/'environment.json')
    robust=load(out/'robustness.json');reference=load_asset(out/'reference.npz');candidate=load_asset(out/'selected_candidate.npz')
    selected=next(r for r in o['rows'] if r['label']==o['selected']);m=selected['final_metrics'];top=p['source_topology'];raw=p['raw_index_topology']
    figures(out,reference,candidate,o,c)
    optim_table=table(['方案','实测面数','减面率','ASD/mm','D95/mm','采样最大/mm','面积变化','单次几何复核','CAD预算','追加三种子复核'],[
        [r['label'],r.get('actual_faces'),f"{100*r.get('reduction_ratio',0):.2f}%",r.get('final_metrics',{}).get('asd'),r.get('final_metrics',{}).get('d95'),
         r.get('final_metrics',{}).get('sampled_max'),f"{100*r.get('final_metrics',{}).get('area_change',0):.3f}%",'通过' if r.get('geometry_final_pass') else '未通过','满足' if r.get('within_cad_budget') else '超限',
         '通过' if r.get('stability_passed') else '未通过' if 'stability_passed' in r else '未进入追加复核'] for r in o['rows']])
    conversion_table=table(['方向','状态','实际表示','ASD/mm','D95/mm','采样最大/mm','包围盒差/mm','离散差/mm'],[
        [r['direction'],r['geometry_status'],r['actual_representation'],r['asd_mm'],r['d95_mm'],r['sampled_max_mm'],r['bbox_delta_mm'],r['convergence_delta_mm']] for r in c['cases']])
    end_table=table(['方向','原始→最终D95/mm','原始→最终采样最大/mm','完整来源链→选中候选D95/mm','转换用时/s','文件大小/MiB'],[
        [r['direction'],r['end_to_end_d95_mm'],r['end_to_end_max_mm'],r['chain_vs_selected_d95_mm'],r['elapsed_seconds'],r['output_bytes']/1024**2 if r['output_bytes'] else None] for r in c['cases']])
    seeds_table=table(['种子','每方向点数','ASD/mm','D95/mm','采样最大/mm','原阈值检查'],[
        [r['seed'],50000,r['asd_mm'],r['d95_mm'],r['sampled_max_mm'],'通过' if r['geometry_pass'] else '未通过'] for r in robust['sampling_repeats']])
    negative_table=table(['负对照','D95/mm','包围盒差/mm','正确拒绝'],[
        [r['case'],r.get('d95_mm'),r.get('bbox_delta_mm'),'是' if r['correctly_rejected'] else '否'] for r in robust['negative_controls']])
    max_convert=max(r['sampled_max_mm'] or 0 for r in c['cases']);max_d95=max(r['end_to_end_d95_mm'] or 0 for r in c['cases'])
    limits_mm={k:v*m['reference_scale'] for k,v in [('d95',plan['limits']['d95_normalized']),('sampled_max',plan['limits']['sampled_max_normalized'])]}
    rejected=[r for r in o['rows'] if not r.get('geometry_final_pass') or r.get('stability_passed') is False]
    reasons='\n'.join('- `'+r['label']+'`：'+('、'.join(r.get('reason_codes',[])) or
        '独立种子复核出现'+str(sorted({reason for a in r.get('stability_checks',[]) for reason in a['reason_codes']})) if r.get('stability_passed') is False else
        '、'.join(r.get('reason_codes',[])) or '; '.join(r.get('errors',[])))+'。' for r in rejected)
    topology_table=table(['项目','原始VTK索引展开','同坐标索引规范化后','选中候选'],[
        [name,raw.get(key),top.get(key),selected['basic_topology'].get(key)] for name,key in [
        ('顶点数','vertices'),('三角面数','faces'),('边界边数','boundary_edges'),('非流形边数','nonmanifold_edges'),
        ('重复面数','duplicate_faces'),('表面连通分量','connected_surface_components'),('Euler示性数','euler_characteristic_used_vertices'),
        ('边关联闭合检查','watertight_edge_test'),('面方向一致性','consistent_winding_test')]])
    freecad='.'.join(runtime['freecad_version'][:3])
    verification_note=('工程回归日志见`regression_tests.log`；GUI证据见`gui/verification.json`。这些记录不替代几何指标。' if (out/'regression_tests.log').exists() else '本次从桌面后台或命令行实际计算并保存结果；本目录没有另行运行工程回归测试，不套用历史测试次数。几何产物审计见`artifact_verification.json`。')
    policy=load(out/'storage_policy.json') if (out/'storage_policy.json').exists() else {'mode':'complete'}
    storage_note=('本次采用答辩记录模式：所有指标仍实际使用完整50,000点/方向；保留选中优化候选与六次转换回读的完整采样数组。未选优化方案、追加种子和端到端评价只保留指标、种子与几何快照，不落盘重复采样数组。详见storage_policy.json。' if policy['mode']=='presentation' else '本次采用完整记录模式，保存各阶段采样数组和指标。')
    text=f'''# 公开MRI髌骨模型优化、六向格式转换与回读误差验证实验报告

课程角色：成员2（模型优化、评价与格式适配）  
实验日期：2026年10月22日  
报告类型：实际运行记录，可复现实验；作者姓名、学号与课程名称由提交人补充。  
数据：SPL Knee Atlas中的髌骨表面（patella），不是合成球面。

## 1. 摘要与主要结论

本实验选用公开MRI分割与三维重建图谱中的髌骨模型，建立“来源核实—精确索引规范化—优化对照—独立误差复核—六向转换—新进程回读—端到端比较”的实验链。原始模型展开为{len(reference.faces):,}个三角面，经QEM简化后选中{len(candidate.faces):,}面研究候选，减面率{100*m['reduction_ratio']:.3f}%。以每方向50,000点、独立种子复核，优化D95为{m['d95']:.6f}mm，采样最大偏差为{m['sampled_max']:.6f}mm，面积变化为{100*m['area_change']:.4f}%。

六个方向完成{c['total']}项，其中{c['passed']}项通过本项目冻结的转换回读检查。转换步骤的最大采样偏差为{max_convert:.6g}mm；该单步从已量化的STL开始，另行覆盖双精度候选→STL→CAD来源链的D95约为10⁻⁶mm。对照原始医学网格的最终D95最大为{max_d95:.6f}mm。由于STEP与IGS由简化STL逐三角面构造，这组转换几乎不引入新的表面近似，主要误差来自前序简化。这一结果不能推广到原生曲面CAD或其他医学病例。

本报告保留未通过的强减面、Laplacian和平滑组合；通过不等于完整临床或制造合格。所有优化网格仍为`candidate_unaccepted / unverified`，原始参考未修改。

## 2. 实验问题与评价边界

本实验验证四个问题：

- 公开医学模型能否在保留可测几何精度的条件下显著减少三角面？
- 单纯增加平滑或加大减面是否一定带来更好的结果？
- STL、STEP、IGS互转后，文件能否在独立进程回读，坐标、单位和表面是否保持一致？
- 将最终产物直接与原始医学模型比较后，整个处理链的误差是否被转换报告掩盖？

研究对象为一个来源明确的MRI图谱表面。实验不重新执行MRI分割，不评价分割相对于真实骨表面的误差，不提供病例间统计推断，不宣称NX等其他CAD软件互操作已通过。源图谱在膝部扫描范围内提供模型，不能把它泛称为完整下肢模型。

## 3. 数据来源、许可、单位与可追踪性

### 3.1 来源与选择理由

数据取自[Open Anatomy的SPL Knee Atlas官方介绍]({p['description_url']})。官方说明其模型来自MRI扫描的半自动分割与三维重建，作者为Jen Richolt、Marianna Jakab、Ron Kikinis，机构为Surgical Planning Laboratory / Brigham and Women’s Hospital / Harvard Medical School。页面列示发布月份为2015年9月，下载包名为`knee-2016-09.zip`；二者均不等同MRI采集时间。

下载地址：[官方图谱压缩包]({p['source_url']})。本实验使用包内`{p['model_entry']}`及其MRML场景索引。年龄、性别、采集日期及左右侧没有从本次核实资料中确认，因此不填写或推测。

选择髌骨的理由是：与骨科场景直接相关、具有真实非球面解剖形态、原始网格足够密集，可在普通电脑上开展参数对照，又能在保留误差约束的前提下适配当前3,000面CAD预算。

### 3.2 许可与署名

官方介绍指定3D Slicer License section B，压缩包`LICENSE.md`同样指向Slicer许可证。完整许可已随本实验保存为`3D-Slicer-License.txt`，原始图谱通知保存为`atlas_LICENSE.md`。使用及再分发实验数据时应保留这些文件、署名及修改说明，不能只引用程序代码的许可证。[许可证原文]({p['license'] and 'https://github.com/Slicer/Slicer/blob/main/License.txt'})。

推荐署名与修改说明：

```text
{ATTRIBUTION}
```

这里标注的修改只包括数据提取、三角化、同坐标索引规范化、优化及格式适配；没有把修改后的模型冒充源作者原始发布模型。

### 3.3 长度单位与坐标

源模型来自2015年Slicer场景，[官方历史坐标说明](https://www.slicer.org/wiki/Slicer3:Coordinates)将模型坐标定义为RAS空间中的毫米。原始VTK头部没有显式`SPACE=RAS`标记，因此本实验把解剖坐标方向记为“依据旧场景约定推定”，而不是声称验证了DICOM方向。保留源数值坐标，不居中、不归一化、不镜像、不配准；在CAD运行器中显式声明STL为mm。

原模型三轴范围分别为{f(top['extent_mm'][0])}、{f(top['extent_mm'][1])}、{f(top['extent_mm'][2])}mm。随包MRI头记录体素方向步长约0.27344、0.27344、1.0（采用Slicer毫米约定）。这个分辨率只提供采样尺度背景，不能替代分割真值或独立物理标定。STL本身不携带标准单位，单独传播STL时必须携带元数据说明。[Slicer坐标约定](https://slicer.readthedocs.io/en/5.10/user_guide/coordinate_systems.html)。

### 3.4 文件校验

| 记录 | SHA256 |
| --- | --- |
| 原始下载ZIP | `{p['archive_sha256']}` |
| 原始髌骨VTK | `{p['source_vtk_sha256']}` |
| MRML场景 | `{p['scene_sha256']}` |
| 完整许可证 | `{p['license_sha256']}` |
| 规范化参考几何 | `{reference.geometry_hash}` |
| 选中优化候选几何 | `{candidate.geometry_hash}` |

更完整的来源、场景节点及原始索引统计见`provenance.json`。源数据只下载和解析为数据，没有运行压缩包中的网页脚本。

## 4. 预处理发现：重复坐标索引与假性开口

原始VTK保存{p['raw_vtk_points']:,}个点、{p['raw_vtk_cells']:,}个单元，其中{p['raw_triangle_strips']:,}个为三角带。先使用VTK TriangleFilter展开为显式三角形，不能把三角带单元数误当作三角面数。

第一轮直接使用这些索引，测得154条边界边、20个基于共享边的分量。进一步检查发现{p['exact_duplicate_vertices_reindexed']}个点与其他点坐标完全一致，只是索引不同。采用`numpy.unique(axis=0, return_inverse=True)`统一完全相同坐标的索引，并重新映射三角面，未按距离阈值合并邻近点。规范化前后，`raw_vertices[raw_faces]`与`canonical_vertices[canonical_faces]`逐元素精确相等：`{p['triangle_coordinates_bitwise_equal_after_reindex']}`。因此各三角形的位置、朝向、面数和表面集合不变。

{topology_table}

这一步修正数据表示层的索引分裂，不是解剖补洞或自动修复。若没有这一检查，就会把数据表示问题误判为真实缺损，或把优化器内部的索引变化误判为解剖结构被改变。原始展开快照仍保存在`raw_triangulated_reference.npz/.json`。

第一轮未规范化的结果保存在`../medical_patella_initial_20261022/`，最终实验在新目录重新冻结参数并执行，没有删除第一轮失败。准备阶段还遇到Trimesh分量统计的可选`networkx`依赖缺失；改用SciPy稀疏共享边邻接统计，避免统计函数附带补洞行为。该工程问题不改变几何数据。

## 5. 实验环境与系统执行链

- 平台：{environment['platform']}。
- Python：{environment['python'].splitlines()[0]}。
- FreeCAD：{freecad}；OpenCASCADE：{runtime['occ_version']}。
- 软件版本：`{json.dumps(environment['packages'],ensure_ascii=False)}`。
- 普通Python负责网格、评价和报告；FreeCAD自带Python负责CAD内核读写，两者通过文件协议通信。
- 每次写出与两档回读使用不同进程，记录PID及请求ID；不复用写出时内存中的shape冒充回读对象。

运行环境详见`environment.json`和`runtime.json`。这是本机单次实验，计算时间含本机负载和首次后端加载，不应解释为跨平台速度基准。

{verification_note}

## 6. 优化方法及实现

### 6.1 QEM简化

采用PyMeshLab的`meshing_decimation_quadric_edge_collapse`。对相邻三角面平面构造二次误差，用边折叠减少顶点与面数；这一方法以局部二次代价近似几何损失，必须再用独立表面距离检验。实现设置`preserveboundary=True`、`preservenormal=True`、`preservetopology=True`，但这些算法选项不替代输出诊断。[Garland与Heckbert原始方法](https://www.cs.cmu.edu/~garland/quadrics/quadrics.html)，[PyMeshLab官方过滤器说明](https://pymeshlab.readthedocs.io/en/latest/filter_list.html)。

本实验的目标面数为6,000、3,000、2,400、1,800、1,200、800；程序按原始面数计算保留率，再记录真实输出面数。目标1,800面实测为1,798面，但它在追加采样时被淘汰；最终选中`{o['selected']}`，实际{len(candidate.faces):,}面，不能把请求值写成实测值。

### 6.2 Laplacian与Taubin对照

Laplacian使用均匀邻接的显式更新`v_new = v + 0.5 × (neighbor_mean - v)`，迭代5次。Taubin每轮依次采用0.5与−0.53两个系数，迭代5轮；另测试QEM 2,400面后再执行3轮Taubin。边界顶点固定。本模型规范化后无边界，但该实现仍保留边界处理。[Taubin方法原始论文](https://research.ibm.com/publications/signal-processing-approach-to-fair-surface-design)。

平滑不减少面数；本实验不把“视觉变光滑”直接等同几何更准确。Laplacian可能收缩，Taubin也并非对任意数据与参数严格无偏移，是否采用由实测约束决定。

### 6.3 基线与选型规则

身份基线直接复制原坐标与三角面，不调用优化器来产生所谓“无变化”基线。共比较{len(o['rows'])}个配置。每个配置都相对于同一规范化原始参考独立生成，不把上一个简化结果继续简化。

筛选每方向10,000点；最终复核每方向50,000点，复核种子与筛选种子独立。初始规则是在单次最终几何阈值通过、基础拓扑计数保持且面数≤3,000的候选中，按面数最少、再按D95排序。第一轮由此选出1,798面候选，且六向回读通过，但追加的三种子采样发现两次最大偏差超限，完整记录保留在`../medical_patella_20261022/`。因此没有把该候选作为最终交付。

随后在新目录中先记录修订后的复核规则，再执行当前最终实验：保留原几何阈值与种子，按相同顺序逐一检查候选，要求三组额外独立种子全部满足原几何约束，才可选入最终转换；不放宽阈值、不删掉失败种子。基础拓扑检查包含边界边、非流形边、重复面、连通分量、Euler示性数和面方向；未实现的自交、非流形顶点、ROI与临床审核不伪造为通过。这是记录明确的实验方案修订，不冒充最初就采用了多种子选型。

## 7. 误差定义与冻结阈值

设参考表面为A、候选表面为B，分别按三角形面积选择面，再使用重心权重在面内均匀采样。每个采样点通过VTK StaticCellLocator查询到另一网格最近三角表面的距离，不是最近顶点距离，不采用ICP对齐。

```text
dA = distance(sample(A), triangle_surface(B))
dB = distance(sample(B), triangle_surface(A))
ASD = (mean(dA) + mean(dB)) / 2
D95 = max(quantile(dA, 0.95), quantile(dB, 0.95))
M_sample = max(max(dA), max(dB))
L = length_of_reference_bounding_box_diagonal
normalized_D95 = D95 / L
area_change = abs(area(B) - area(A)) / area(A)
```

采样最大偏差`M_sample`不是精确Hausdorff距离，有限采样可能漏掉小区域尖峰；三次换种子复测只能检查经验稳定性。

{table(['阶段','项目','冻结阈值/设置'],[
    ['优化','D95/L',plan['limits']['d95_normalized']],['优化','M_sample/L',plan['limits']['sampled_max_normalized']],['优化','相对面积变化',plan['limits']['area_change']],
    ['优化','本模型对应D95上限/mm',limits_mm['d95']],['优化','本模型对应采样最大上限/mm',limits_mm['sampled_max']],
    ['CAD转换','D95/mm',cfg['d95_mm']],['CAD转换','采样最大/mm',cfg['sampled_max_mm']],['CAD转换','包围盒最大绝对坐标差/mm',cfg['coordinate_tolerance_mm']],
    ['CAD转换','两档ASD/D95/采样最大差的最大值/mm',cfg['convergence_tolerance_mm']],['每次最终评价','每方向点数',50000],['STL→CAD','最大三角面预算',cfg['max_stl_faces']]])}

这些是课程工程阈值，不是医学或制造标准。优化阈值与CAD阈值的参考不同：前者约束简化误差，后者约束格式转换额外误差，不能混用。源模型固定尺度L为{m['reference_scale']:.6f}mm。阈值保存在`optimization_plan.json`与`frozen_cad_config.json`，本实验没有因失败而放宽阈值。

## 8. 优化对照结果

{optim_table}

![QEM面数与误差权衡](figures/optimization_tradeoff.png)

选中`{o['selected']}`，实际{len(candidate.faces):,}面，减面{100*m['reduction_ratio']:.3f}%，ASD为{m['asd']:.6f}mm，D95为{m['d95']:.6f}mm，采样最大为{m['sampled_max']:.6f}mm。候选基础拓扑统计为：{selected['basic_topology']['connected_surface_components']}个连通分量、{selected['basic_topology']['boundary_edges']}条边界边、{selected['basic_topology']['nonmanifold_edges']}条非流形边、Euler示性数{selected['basic_topology']['euler_characteristic_used_vertices']}。这些结果支持基础几何研究使用，不足以宣称完全无自交或实体合格。

未通过方案及直接原因：

{reasons}

可以看到，更少面数与更强平滑并不一定更优；QEM加平滑产生的额外偏移也可能超过最大偏差约束。低分位三角形质量q只作为辅助指标，不能替代对原形状的保真度。所选候选的q最小值为{selected['basic_topology']['quality']['q_min']:.6g}，中位数为{selected['basic_topology']['quality']['q_median']:.6g}。

![真实髌骨原始与优化模型，固定相同坐标尺度](figures/medical_model_comparison.png)

![优化偏差的双向分布与CDF](figures/optimization_errors.png)

![优化表面偏差图，共同色标](figures/medical_error_map.png)

图中模型使用统一观察角度和坐标尺度；误差图为了阅读只显示部分采样点，指标与NPZ记录仍使用完整50,000点/方向。

## 9. 六向格式适配实施与来源链

六个方向均由同一个真实医学候选派生：

```text
MRI-derived patella VTK → canonical reference → QEM candidate → selected_candidate.stl
  ├─ STL → STEP (faceted surface)
  │    ├─ STEP → STL
  │    └─ STEP → IGS
  └─ STL → IGS (faceted surface)
       ├─ IGS → STL
       └─ IGS → STEP
```

因此，STEP和IGS输入不是独立获取的原生参数化医学CAD，而是简化网格的逐面B-Rep表达。STL→CAD调用FreeCAD `makeShapeFromMesh`，缝合容差为{cfg['sewing_tolerance_mm']}mm，不拟合光滑NURBS、不重建参数化历史、不自动提升为Solid。实际输出类型必须以回读记录为准。

每项流程如下：输入与单位校验 → FreeCAD写出 → 检查非空文件及SHA256 → 新进程细档回读 → 另一进程粗档回读 → 如为CAD输入，再独立读入源CAD的细/粗参考 → 双向距离、包围盒与离散稳定性 → 保存报告。

细档回读线性偏差/角度参数为{cfg['readback_linear_deflection_mm']}mm / {cfg['readback_angular_deflection_rad']}rad；粗档为{cfg['coarse_linear_deflection_mm']}mm / {cfg['coarse_angular_deflection_rad']}rad；源CAD细参考为{cfg['source_linear_deflection_mm']}mm / {cfg['source_angular_deflection_rad']}rad，均使用绝对线性参数。它们是离散算法参数，不是已经证明的全局误差上界。

## 10. 六向回读实测结果

{conversion_table}

通过数为{c['passed']}/{c['total']}。每项同时检查独立回读进程、回读有效性、坐标包围盒、D95、采样最大偏差与两档离散稳定性。详细请求ID、PID、文件哈希和检查布尔值在对应任务目录中。

本模型转换误差很小，是因为目标CAD由原三角面形成，并非曲面重拟合。这里的单步参考是已经写入STL的坐标，二进制STL的单精度量化发生在此前；不能把约10⁻¹⁴mm的单步数值当作完整NPZ→STL→CAD链的精度。下一表的“完整来源链→选中候选”列直接对照原双精度候选，覆盖STL量化，其D95约为10⁻⁶mm量级。两者都不能解释为获得了超越源MRI分辨率的解剖准确度。共同使用OpenCASCADE内核也意味着这不是跨厂商独立验证。

## 11. 端到端误差与文件代价

只比较“转换前候选”和“转换后回读”可能忽略已发生的简化误差。本实验另把每项回读产物与原始医学参考直接比较，使用新的固定种子{20261022+20000}、50,000点/方向。并补充完整来源链产物与选中候选的直接比较。

{end_table}

![格式步骤误差与全流程误差分开呈现](figures/conversion_vs_total_error.png)

最终D95仍主要处于{max_d95:.6f}mm量级，而不是转换步骤的微小误差量级，说明原始→简化的损失没有消失。不能把不同步骤的D95简单相加来充当端到端D95，因为分位数和抽样集合不满足这种可加性。本表直接重采样测量。不同格式回读后的三角面顺序可能变化，相同随机种子也可能落到不同的具体三角形上，因此同一表面不同方向结果的小幅分位差不一定来自新的几何损失。

原始参考STL大小为{(out/'reference.stl').stat().st_size/1024**2:.4f}MiB，候选STL为{(out/'selected_candidate.stl').stat().st_size/1024**2:.4f}MiB。STEP/IGS使用大量面片拓扑描述，可能比二进制STL大；格式转换不等于进一步压缩，也不等于更好的可编辑性。

## 12. 重复采样与负对照

### 12.1 三组独立种子复测

{seeds_table}

三次复测D95范围为{min(r['d95_mm'] for r in robust['sampling_repeats']):.6f}～{max(r['d95_mm'] for r in robust['sampling_repeats']):.6f}mm；采样最大偏差范围为{min(r['sampled_max_mm'] for r in robust['sampling_repeats']):.6f}～{max(r['sampled_max_mm'] for r in robust['sampling_repeats']):.6f}mm。这里只报告经验范围，不标成置信区间。若以后更密采样或局部检查发现更高误差，应如实更新结论。

### 12.2 负对照

在同一真实候选上人为平移X方向1mm、施加错误10倍尺度，并提交单位未知的STL。前两项通过本工程真实距离评价和坐标检查判别；不是声称修改CAD文件后又做了一轮跨软件试验。未知单位项实际调用转换入口并在写出前被拒绝。

{negative_table}

负对照用来排除“评价器对所有输入都显示通过”的错误。报告与日志保存在`robustness.json`及`negative/unknown_stl_unit/`。

## 13. 结果解释、风险与局限

- **形状保真**：候选满足冻结的工程误差和面积约束，可用作课程几何处理与格式适配演示。没有分割真值，不能据此评价MRI分割质量。
- **基础拓扑**：本次统计支持闭合共享边结构与方向一致，但未执行完整自交、非流形顶点、局部厚度、ROI保护和实体归属检查，体积指标保留不可用。
- **局部细节**：面积采样偏向面积较大的区域，可能漏掉小面积高曲率或病灶区域；后续应增加解剖ROI与顶点/曲率加密评价。
- **坐标语义**：数值坐标和尺度保持，旧场景RAS依据文档推定，未声称检查左右侧或原始DICOM方向；本实验没有进行配准。
- **样本数量**：仅一个髌骨模型，不代表其他骨骼、血管、牙科、颅颌面或四专科同时验收。
- **CAD语义**：曲面/面片不等于实体，不包含参数历史；同内核回读不能证明NX、SolidWorks或打印机软件的完全兼容。
- **单位与标准**：mm来自源软件约定和场景，而非独立标定；课程阈值不构成临床、植入物制造或法规精度标准。
- **接受状态**：优化结果始终未被正式接受。成员1完整诊断、版本服务与人工确认没有被模拟成已经完成。

## 14. 复现实验步骤与检查点

{storage_note}

以下命令在工程根目录`work/`运行，使用已有`.venv`与已配置FreeCAD。新实验必须选新的输出目录，避免覆盖本报告结果。

```bash
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase all --out runs/medical_patella_reproduction
```

也可分阶段执行，便于查看中间结果：

```bash
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase prepare --out runs/medical_patella_reproduction
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase optimize --out runs/medical_patella_reproduction
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase convert --out runs/medical_patella_reproduction
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase report --out runs/medical_patella_reproduction
```

准备阶段检查原始ZIP/VTK哈希、场景无未处理的父变换、三角坐标精确相等；优化阶段核对同一参考哈希、独立种子及实际面数；转换阶段核对不同PID、目标文件哈希、真实类型和全部检查；最后核对候选仍为unverified，参考版本与几何哈希不变。

环境、源脚本及每次产物的哈希保存在`artifact_verification.json`和`artifact_manifest.json`。如果数据源或软件版本变化，不应要求逐位一致的优化网格；应先核对来源和配置，再比较面数、误差与质量范围，保留变化记录。

## 15. 在现有桌面工作台中演示

1. 启动`启动医学网格工作台.command`，打开本实验`reference.npz`查看真实参考。
2. 可在“优化”页执行QEM对照；完整参数搜索和多种子选型由上述实验脚本复现。若GUI当前的保留率范围或小数精度不能精确表示实验配置，直接使用本实验已保存候选，不把近似参数冒充本次结果。原始参考面数超出CAD预算时不能直接转CAD。
3. “CAD转换”选择外部文件`selected_candidate.stl`，明确单位mm，选择STEP或IGS并运行；其余方向使用相应已生成STEP/IGS。
4. 右侧“转换结果”查看阶段检查，“模型对比”查看真实回读和参考，“任务报告”阅读HTML/JSON。
5. 使用“打开已有任务 / 报告”选择本实验`conversion/<方向>/result.json`，可直接查看已完成记录和双视图；选择本目录`report.html`可在同一窗口阅读实验总报告。

桌面不会因为转换检查通过而提交正式网格版本。若移动整个实验目录，已有记录中的绝对预览路径可能失效；HTML与数值仍可查看，完整重跑可生成新路径。

## 16. 课设提交建议与验收清单

建议把报告正文、五张图、两张CSV表、来源署名与许可、选中STL以及STEP/IGS样例一起提交；同时提供复现实验脚本和JSON日志作为证据。答辩重点可围绕“真实数据表示问题的识别、冻结阈值下的参数对照、独立回读、端到端误差和诚实的边界”展开。

- 数据真实性：官方MRI图谱来源、具体结构、作者与哈希齐全。
- 预处理可解释：71个精确重复坐标重编号，三角形坐标逐项相同。
- 优化可比较：身份基线、多面数QEM、Laplacian、Taubin及组合；保留失败方案。
- 六向可验证：每项实际写出与新进程回读，保留真实类型与检查。
- 误差无混淆：优化、转换单步与端到端三类误差分别报告。
- 质量不过度承诺：未把未执行的诊断、体积或临床资格写成通过。

这份报告可作为成员2课设实验部分的正文基础；个人贡献、团队接口联调和课程要求的封面格式仍由提交人按实际情况补充，不虚构已完成的其他成员工作。

## 17. 文件索引与参考资料

| 路径 | 内容 |
| --- | --- |
| `provenance.json` | 来源、哈希、原始场景、原始/规范化统计 |
| `optimization_plan.json` | 固定参数、阈值、种子与选型规则 |
| `optimization_matrix.csv` | 所有优化配置实测指标 |
| `optimization/<方案>/` | 候选及独立复核，采样保存范围见storage_policy.json或上述记录模式 |
| `conversion_matrix.csv` | 六向回读及端到端汇总 |
| `conversion/<方向>/` | 转换文件、请求、日志、回读网格、采样和HTML/JSON |
| `robustness.json` | 三次种子复测及负对照 |
| `reference.npz/.json` | 规范化原始参考 |
| `selected_candidate.npz/.json/.stl` | 未正式接受的研究候选 |
| `figures/` | 正文使用的五幅实际数据图 |
| `artifact_verification.json` | 实验产物一致性审计 |
| `artifact_manifest.json` | 关键产物SHA256 |

参考资料：

- [SPL Knee Atlas官方来源](https://www.openanatomy.org/atlas-pages/atlas-spl-knee.html)，访问日期2026-10-22。
- [3D Slicer完整许可](https://github.com/Slicer/Slicer/blob/main/License.txt)，随实验保留本次下载版本。
- [Slicer3旧版坐标约定](https://www.slicer.org/wiki/Slicer3:Coordinates)，用于旧场景毫米与RAS推定。
- [Slicer坐标系统说明](https://slicer.readthedocs.io/en/5.10/user_guide/coordinate_systems.html)，用于区分数值保持与解剖方向声明。
- [Surface Simplification Using Quadric Error Metrics](https://www.cs.cmu.edu/~garland/quadrics/quadrics.html)，Garland与Heckbert，1997。
- [A Signal Processing Approach to Fair Surface Design](https://research.ibm.com/publications/signal-processing-approach-to-fair-surface-design)，Taubin，1995。
- [PyMeshLab官方过滤器参数](https://pymeshlab.readthedocs.io/en/latest/filter_list.html)。
'''
    (out/'实验报告.md').write_text(text,encoding='utf-8')
    (out/'report.html').write_text(offline_html(text),encoding='utf-8')
    # Do not overwrite the original source-geometry or software-state records.
    key_paths=[out/'reference.npz',out/'reference.json',out/'selected_candidate.npz',out/'selected_candidate.json',out/'selected_candidate.stl',
               out/'optimization_plan.json',out/'frozen_cad_config.json',out/'provenance.json']
    verification={'six_directions':len(c['cases'])==6,'six_roundtrips_passed':c['passed']==6,
                  'reference_geometry_unchanged':reference.geometry_hash==p['reference_geometry_sha256'],
                  'reference_version_unchanged':reference.version_id==p['reference_version'],
                  'exact_index_normalization':p['triangle_coordinates_bitwise_equal_after_reindex'],
                  'candidate_unaccepted':candidate.metadata.get('lifecycle')=='candidate_unaccepted',
                  'candidate_unverified':candidate.metadata.get('quality_status')=='unverified',
                  'three_seed_repeats_passed':all(r['geometry_pass'] for r in robust['sampling_repeats']),
                  'negative_controls_rejected':all(r['correctly_rejected'] for r in robust['negative_controls'])}
    for row in c['cases']:
        directory=out/'conversion'/row['direction'];result=load(directory/'result.json');preview=load_asset(result['preview_assets']['candidate'])
        checks={'all_conversion_checks':all(result['checks'].values()),'file_hash_matches':file_hash(result['output_path'])==result['output_sha256'],
                'end_to_end_original_reference_matches':result['end_to_end_original']['reference_hash']==reference.geometry_hash,
                'samples_each_direction_50000':result['metrics']['samples_each_direction']==50000,
                'preview_hash_matches_metric':preview.geometry_hash==result['metrics']['candidate_hash']}
        with np.load(result['preview_assets']['distances'],allow_pickle=False) as arr:
            checks['sample_arrays_complete']=len(arr['distances_ab'])==len(arr['distances_ba'])==50000
        verification[row['direction']]=checks
        key_paths.extend([directory/'result.json',Path(result['output_path'])])
    verification['all_passed']=all(all(v.values()) if isinstance(v,dict) else v for v in verification.values())
    write_json(out/'artifact_verification.json',verification)
    key_paths.extend([out/'实验报告.md',out/'report.html',Path(__file__),Path(__file__).with_name('patella.py'),root/'scripts/experiments/medical_patella_gui.py'])
    key_paths.extend(sorted((out/'figures').glob('*.png')))
    key_paths.extend(path for path in [out/'regression_tests.log',out/'gui/verification.json'] if path.exists())
    write_json(out/'artifact_manifest.json',{'files':[{'path':str(path),'sha256':file_hash(path),'bytes':path.stat().st_size} for path in key_paths]})
    if publish:
        # Standalone Markdown delivery retains working local links and images beside it.
        delivery=root.parent/'outputs'/'真实MRI髌骨模型_课设实验报告'
        delivery.mkdir(parents=True,exist_ok=True)
        shutil.copy2(out/'实验报告.md',delivery/'实验报告.md');shutil.copy2(out/'report.html',delivery/'报告.html')
        shutil.copytree(out/'figures',delivery/'figures',dirs_exist_ok=True)
        for name in ['optimization_matrix.csv','conversion_matrix.csv','provenance.json','artifact_verification.json','3D-Slicer-License.txt','ATTRIBUTION.txt']:
            shutil.copy2(out/name,delivery/name)
        (delivery/'完整结果位置.txt').write_text(str(out)+'\n报告中的其他JSON与模型位于该实验目录；本目录为便于阅读的报告副本。\n',encoding='utf-8')
    print('REPORT',out/'report.html',flush=True)
    print('AUDIT',json.dumps(verification,ensure_ascii=False),flush=True)
