# 医学三维网格工作台成员2

这是成员2的可运行工程，已完成基础网格原型、本机FreeCAD六向转换与桌面集成，并在公开MRI来源的真实髌骨模型上完成优化、六向回读及端到端误差实验。成员1正式诊断和版本服务仍待接入；实验通过不等于医学模型完整资格检查。

## 先运行

**最新答辩入口：双击`启动髌骨答辩演示.command`。** “课设演示”页的一键按钮会在后台重新计算公开MRI髌骨的十组优化、三种子复核、六向转换回读、负对照及新报告；也可明确选择只载入历史结果。所有指标和报告在同一窗口查看。操作与44项测试及真实GUI验收见[答辩演示说明](docs/phase5_patella_demo.md)。

默认答辩记录模式保留必要的完整预览采样，所有最终指标仍使用50,000点/方向；完整中间采样可勾选。已加入保存目录选择与磁盘空间检查，演示不覆盖此前交付的医学实验报告。

在本目录执行。当前机器已建立本地`.venv`；`./run`自动使用本工程环境和源码。换机器请先执行后面的安装步骤。

```bash
./run fixtures
./run evaluate --reference data/generated/plane.npz --candidate data/generated/plane_shifted.npz --samples 1000
./启动医学网格工作台.command
```

macOS也可以双击同目录的`启动医学网格工作台.command`。初次打开默认加载合成球面，点击“生成候选并复核”。结果显示为`needs_review / unverified`是正确行为：几何约束可以通过，但成员1结构复检没有提供，程序不会自动接受正式版本。

桌面支持打开模型、QEM/两类平滑/重划分、九候选搜索、前后相机同步、双向采样误差色图、候选表、取消、预览包保存，以及STL/STEP/IGS六向转换、独立回读、窗口内HTML/JSON报告和历史任务重开。桌面操作与本轮完整验收见[第三阶段说明](docs/phase3_desktop.md)。

进入“CAD转换”，选择外部文件、当前参考网格或所选优化候选，选择目标格式；STL必须确认单位，再点击“转换并回读验证”。右侧“转换结果 / 模型对比 / 任务报告”在同一窗口展示检查、双视图和报告。无需另开FreeCAD界面或浏览器。保存目录内保留转换文件、回读快照与检查记录。

## 安装和测试

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python scripts/gui_smoke.py
PYTHONPATH=src .venv/bin/python scripts/gui_cad_smoke.py
```

Windows将`.venv/bin/python`换成`.venv\Scripts\python.exe`，创建环境可用`py -3.12 -m venv .venv`。

Qt采用`PySide6-Essentials`，它提供本工程使用的Core/Gui/Widgets绑定；不安装当前阶段用不到的WebEngine等扩展。进程和运行版本记录见`runs/environment/result.json`及平台依赖锁。

## 命令行示例

### 单次和九候选优化

```bash
./run optimize --input data/generated/sphere.npz --operation qem --ratio 0.5
./run optimize --input data/generated/open_tube.npz --operation taubin --iterations 5
./run optimize --input data/generated/sphere.npz --operation remesh --edge 2 --iterations 3
./run optimize --input data/generated/sphere.npz --search --limits configs/limits.json
```

默认每方向筛选10000点、独立种子最终复核至少50000点。调试可指定`--samples 1000 --final-samples 3000`，结果明确记录实际点数。三项默认阈值是调试起点，不是医学精度标准。

每次输出到新的`runs/<任务名_随机ID>/`，包含请求、参考快照、候选、采样点和距离数组、JSON、CSV、误差图及HTML。可用`--out`指定新的目录，已有结果目录不会直接覆盖。

### 导入成员1交接包或STL预览

正式交接使用NPZ加同名JSON，见`docs/interface_contract_v1.md`。开发预览STL可显式指定单位：

```bash
./run import-preview --input /absolute/path/input.stl --unit mm --output data/my_input.npz
```

不填写单位则保留未知。STL预览只做完全相同坐标的共享顶点规范化，记录为成员2适配器，不替代成员1原始缺陷检测。PLY/OBJ仅支持本原型能读取的单个三角网格。

### 评价、环境与报告

```bash
./run evaluate --reference data/generated/plane.npz --candidate data/generated/plane_subdivided.npz --samples 1000
./run probe --out runs/environment
./run report --run-dir runs/你的任务目录
```

评价使用面积采样到最近三角表面，ASD为两方向均值的平均，D95为两方向95分位的较大值，采样最大偏差不等于精确Hausdorff。单位未知不输出毫米。此阶段体积始终不可用，因为尚无可靠闭合、自交和实体归属检查。

### 已配置的CAD转换

本机已安装FreeCAD 1.1.4，当前可用配置为`configs/freecad.local.json`，命令默认自动读取。更换电脑时复制`configs/freecad.example.json`并调整运行器路径。普通Python不直接导入FreeCAD；配置中的`{script}`由程序替换为worker绝对路径。

```bash
./run convert --input data/generated/sphere.stl --target step --unit mm --config configs/freecad.local.json
```

已实际通过4类几何×6方向的24项转换，以及8项预期失败和厘米到毫米测试。每项使用新进程两档回读，最终每方向50000点。报告见`runs/cad_validation_50k/report.html`，完整安装及复现记录见`docs/phase2_freecad.md`。面数超限会拒绝；STL转CAD仍只允许面片/曲面策略，不宣称有效实体。

## 成员1接入

1. 先共同审核`docs/interface_contract_v1.md`，当前是协议提案。
2. 提供正式NPZ/JSON和`diagnose_pair(reference, candidate)`适配函数。
3. CLI用`--provider your_package.adapter:diagnose_pair`加载；GUI当前保持待复核模式，正式版本服务在后续集成。
4. 导入、诊断、修复面板通过`MainWindow.register_page`接入。公共`show_mesh`和`highlight_faces`带版本校验。
5. 优化模块返回结果，不直接修改当前已接受版本。正式提交应调用成员1版本服务，并由用户接受。

## 公开医学模型实验（2026-10-22）

使用Open Anatomy发布的SPL Knee Atlas髌骨：MRI分割重建来源，许可为3D Slicer License section B。原始49,862面；最终选择2,400面（减面95.19%），优化D95约0.03059mm，追加三组独立种子全部通过，六向转换6/6通过。初选1,798面在复测中超限，完整保留，未放宽阈值。

详细报告：`runs/medical_patella_verified_20261022/实验报告.md`与`report.html`；关键产物审计见同目录`artifact_verification.json`。图表、优化/转换CSV、许可、源文件哈希和逐项日志均在该目录。便于阅读的副本在上级`outputs/真实MRI髌骨模型_课设实验报告/`。

```bash
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase all --out runs/medical_patella_reproduction
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella_gui.py --out runs/medical_patella_verified_20261022
```

新实验需新的输出目录。数据源需要联网下载77MiB ZIP，本地已缓存；第一次导入VTK/PyMeshLab可能较慢。复现脚本保存原始展开快照，并只规范化完全相同坐标的索引，不按距离合并邻近点。更完整的操作与边界见报告第14至17节。

## 当前边界

- 已增加一个公开MRI图谱髌骨模型的真实数据实验；原有合成几何仍用于回归，不声称覆盖多病例或四专科。
- 未提供成员1接口时只做几何预览，不声明完整拓扑、自交、开口或ROI保护已通过。
- 固定边界Laplacian/Taubin已实现；重划分、简化仍需要正式输出结构复检。
- 体积、边界/分量几何对应、ROI加密和真实医学E3至E6仍为下一阶段任务。
- 六向转换已在合成几何及一个真实MRI图谱表面上验证；独立原生CAD、多病例、NX兼容及自动实体资格尚未验证。
- 原型无正式版本接受按钮，避免预览结果被当作已验证模型。
- 任务取消按本机macOS/POSIX进程组设计；Windows进程树清理还需平台适配与验证。

## 目录

`src/medical_mesh/core`模型与交接；`evaluation`评价；`optimization`候选；`cad`外部运行器；`jobs`协议和后台任务；`ui`公共窗口；`reporting`报告；`tests`实际风险验证；`docs`协议和执行记录。

下一步接入成员1真实诊断及版本服务，增加局部ROI与多病例验证。历史记录见`docs/phase1_status.md`、`docs/phase2_freecad.md`；桌面集成见`docs/phase3_desktop.md`；真实MRI实验见上述最终报告。
