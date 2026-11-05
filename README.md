# 医学三维模型修复与格式适配：统一工作台

依据用户提供的详细实施方案和《两人均衡分工与系统集成方案》，实现成员1的五项职责：数据准备与导入显示、缺陷检测、受控修复、公共模型与版本记录、E1/E2 实验。代码、真实模型、可复现样本、测试、实测结果及页面截图均已放在本目录。

2026-11-04 已把导入、修复、优化、评价和格式适配整理为同一任务，界面按“检查与修复 → 简化与平滑 → 误差与对比 → 格式与导出”组织。顶部打开/检查/回退/保存、中央画布、左侧参数、右侧结果报告和底部预览接受/放弃保持固定位置。合并版没有自动演示或启动加载样例。使用方式见 [统一流程操作](docs/统一流程与优化操作.md)，实际E-3D优化对照见 [优化对照报告](results/e3d_optimization/优化对照与统一流程报告.md)。

## 直接启动

本机依赖已安装到 `.venv`。双击 **启动医学三维工作台.cmd**；原来的 **启动成员1.cmd** 也打开统一工作台。或在本目录执行：

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe start.py
```

另一台 Windows / Python 3.11 电脑：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock-windows.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe start.py
```

锁定文件记录实际验证环境的依赖闭包。2026-10-29 已按锁定文件将运行依赖完整安装到项目 `.venv`，不再依赖系统或用户目录中的数值库；早期环境记录在 `results/E1_E2/environment.json`。其他平台需重新验证依赖和图形驱动。若需要运行可选的第三方软件研究脚本，另安装 `requirements-research.in`。

## 操作与示范流程

后续优化（2026-10-29）：新增双面组合删除/顶点拆分建议、候选预算、后台阶段与取消、大模型简化显示、单位尺寸核对，以及可往返导入并回退的 `.m3d` 项目包。完整说明和10万/50万面测量见 [后续优化与大模型验证](docs/后续优化与大模型验证.md)。

2026-10-29 新增同步双视图、变化面着色和补片质量指标。生成预览后，绿色表示新增面，红色表示修复前被删除的面，橙色表示翻转面；底部显示最小角、最大长宽比及接缝法线夹角。操作和指标定义见 [修复变化与补片质量](docs/修复变化与补片质量.md)。

2026-10-22 增加 E-3D 对照参考后的审核流程：点击“生成修复预览”后，先看前后指标，通过底部下拉框切换修复前/后，再点击“接受预览结果”或“放弃预览”。未接受候选不会提交到版本库，也不会传给成员2。底部确认按钮固定显示；新增视口右键选孔、透明度、标准方向及截图。研究证据与权限限制见 [E3D对照研究与改进](docs/E3D对照研究与改进.md)。以下操作中的修复结果均需显式接受后才成为当前版本。

显示修正（2026-10-22）：黄色仅表示边界或异常边，紫色表示退化线段/异常顶点；不再显示无关黄色散点。诊断列表区分边数、顶点数与涉及面数。方向冲突显示橙色公共边遍历箭头及青色法线。选中对象后可点击“定位并放大选中对象”查看局部表面，裁切外缘不代表缺陷；“恢复全貌”返回完整模型。说明区会解释当前颜色含义。

1. **清理重复面**：导入 `data/damaged/duplicate.stl`，检测列表显示1个重复面；点击该项高亮，勾选“删除重复面”，执行修复；重复面变为0，可回退到原版本。
2. **指定补洞**：导入 `data/damaged/hole.npz`，选中边界，选择“待补孔洞”并点击“标记选中边界”，再生成预览。只处理已标记目标；天然开口和待判断闭环保留。平面模式拒绝非共面环；可显式选择实验局部二次曲面模式，仅支持稳定拟合的简单凸孔，强制自交复检。标记会保存到会话目录，导出另附边界用途 JSON。
3. **医学模型**：导入 `data/medical/FMA7197.stl`（肝脏）、`FMA24474.stl`（右股骨）或 `FMA7204.stl`（右肾），旋转、缩放、切换线框。单位无证据时保持“未知”。人工损坏及修复案例在 `results/medical_E1_E2/`。
4. **非流形候选**：导入 `data/damaged/non_manifold_edge.npz`，点击“查找删面组合 / 顶点拆分建议”。主动选择方案后点击“查看方案并填入删除面编号”，检查局部位置和边界/分量变化，再生成预览并决定接受或放弃。默认验证12个候选，预算可调至48；超过50000面暂不执行整模逐候选复检。不会自动选择方案。顶点拆分示例为 `data/reference/bowtie_vertex.npz`，拆分后建议使用NPZ/项目包交接；STL回读可能重新焊接。开放缺陷链可在明确删面方案中改变；天然开口强制保留。
5. **自交检查**：勾选“检测自交”后重新检测。不可用或失败时显示 `unverified`，结果中的 `face_ids` 为 `null`，不能当作0。

导入单位仅记录比例，不改变坐标；STL 本身不带标准单位信息，重新读取 STL 时需重新确认单位。NPZ 会保留单位与版本。二进制 STL 坐标为 float32，精度交接使用 float64 NPZ。

## 文件与成果

|位置|内容|
|---|---|
|`src/medical_mesh/core/`|MeshAsset、任务结果协议、磁盘版本快照、回退及更新通知|
|`src/medical_mesh/io/mesh_io.py`|严格 STL 读写、输入校验、精确坐标焊接及原始映射；PLY/OBJ 辅助读入|
|`src/medical_mesh/detection/`|自主边面邻接、重复/退化面、边界环、非流形边/顶点、方向冲突、连通分量|
|`src/medical_mesh/processing/`|选定目标修复、复检与候选拒绝、JSON/NPZ 工作进程|
|`src/medical_mesh/ui/member1_panel.py`|可嵌入公共窗口的导入/诊断/修复页|
|`src/medical_mesh/ui/preview_host.py`|本次独立验证用的主窗口与 ViewerAdapter，供成员2替换或复用|
|`data/manifest.csv`|3个真实解剖模型的来源、许可、哈希、单位与观察结果|
|`data/reference/`、`data/damaged/`|解析模型、特殊拓扑和固定种子损坏样本|
|`results/E1_E2/`|17项合成实验 CSV、JSON、前后模型、截图及实验报告|
|`results/medical_E1_E2/`|3器官×4缺陷的12项实测、原始自交诊断和截图|
|`results/gui_verification/`|实际 Qt/VTK 窗口截图与自动操作验证结果|
|`docs/成员1课程报告.md`|数据、算法、结构保护、实验与失败分析章节|
|`docs/接口交接.md`|成员2接入协议与最小函数/工作进程示例|

## 测试与重跑

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/generate_primitives.py
.\.venv\Scripts\python.exe scripts/run_experiments.py
.\.venv\Scripts\python.exe scripts/run_medical_experiments.py
.\.venv\Scripts\python.exe scripts/smoke_gui.py
.\.venv\Scripts\python.exe scripts/verify_guided_repair.py
.\.venv\Scripts\python.exe scripts/verify_visual_review.py
.\.venv\Scripts\python.exe scripts/run_extended_validation.py --large
.\.venv\Scripts\python.exe scripts/verify_delivery_workflow.py
.\.venv\Scripts\python.exe scripts/run_optimization_checks.py
```

`smoke_gui.py` 会短暂显示窗口并自动关闭。`run_experiments.py` 和医学实验会覆盖同名结果文件；版本快照使用独立 ID。重新下载模型可执行 `scripts/fetch_medical_models.py`，已有文件会复用。

## 交接边界

优化、误差评价、STEP/IGS转换及HTML/JSON/CSV报告已接入同一工作流程，模型通过显式适配服务交接。本机已配置项目内便携FreeCAD，24项六向转换、8项异常处理、单位转换及六方向桌面操作验证全部通过，完整回归145项通过。E-3D当前可访问入口未找到等效STEP/IGS转换，不能报告双方数值胜负，详见[专项验证报告](results/cad_six_directions/专项验证报告.md)。体积只对复检通过的单闭合壳体报告；多壳体实体归属、ROI及多病例验证仍不属于已完成能力。接口说明见 `docs/接口交接.md`，运行和本机验证见 [任务二合并说明](docs/任务二合并说明.md)。

默认小孔修复采用自主投影耳切算法，限简单近共面环。新增实验模式利用孔边邻域拟合二次曲面，以拟合中心构造扇形补片；仅支持6—64边的简单凸孔，限制拟合残差、中心偏移与最小三角形角度，强制自交复检。这不是通用曲率补洞或原解剖形状恢复。法线仅做相邻面一致化，不猜测多层壳体内外。复杂自交目前检测并报告，尚无通用自动修复路径。拓扑检查通过但未做自交检查时质量仅为 `diagnosed`。最新使用方式、验证和限制见 [对照后优化](docs/对照后优化.md)。

2026-11-03 完成复杂非流形与曲面补洞专项：8个主样例、5项补充试验，13个E-3D实际导出逐项复核。结论、曲面误差和适用限制见 [专项对照报告](results/e3d_complex/专项对照报告.md)。

2026-11-04 根据专项结果新增多邻域非流形组合建议、支持凹孔与内部加点的邻域曲面模式，以及STL实际回读检查。重启后在补洞方法中选择“邻域曲面补片”，标记目标孔和天然开口，生成预览后审核接受。本轮四类曲面控制孔全部通过。补齐固定孔边的内部顶点角度优化，高曲率控制孔最小角从5.49°提升到12.68°；新增“分壳STL集合 (*.stlset.zip)”导出，逐壳回读验证拓扑与自交，为粘连壳体提供保持对象分离的交接方式。单文件STL合并焊接仍可能粘连，集合中的文件须独立导入。算法预算、逐例结果及采样误差见 [优化验证报告](results/specialist_optimization/优化验证报告.md)。验证：92项自动测试通过，实际Qt/VTK界面完成新模式、后台预览、接受及分壳导出流程检查。补片质量仍应结合预览审核。

医学数据来自 [BodyParts3D 3.0 的 STL 镜像及许可说明](https://github.com/Kevin-Mattheus-Moerman/BodyParts3D)，是同一个男性图谱的不同器官，不应计为多个独立患者。第三方声明见 `THIRD_PARTY_NOTICES.md`。
