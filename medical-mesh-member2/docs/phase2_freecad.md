# FreeCAD安装配置与六向转换验证记录

执行日期：2026年10月18日。

## 已完成的结果

FreeCAD 1.1.4 Apple Silicon版已通过Homebrew安装到`/Applications/FreeCAD.app`。命令行运行器、项目配置、六条转换路径、新进程回读、单位坐标检查及双向误差评价均已实际运行。

最终验收使用4类合成几何，每类执行6个方向，共24项；**24/24项通过**。另有8项预期拒绝/失败测试全部符合预期，厘米STL到毫米的转换也通过。最终每方向采样50000点，筛查与最终验收使用不同固定种子，回读采用两档离散精度。

最终报告位于工程的`runs/cad_validation_50k/report.html`，机器可读结果为同目录`summary.json`，矩阵为`conversion_matrix.csv`。每项子目录保留输入请求、FreeCAD日志、写出文件、回读网格、采样距离数组和完整JSON。

## 安装来源和真实运行环境

- 官方发布：[FreeCAD 1.1.4](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4)。
- 安装命令：`HOMEBREW_NO_AUTO_UPDATE=1 brew install --cask freecad`。
- 安装包：`FreeCAD_1.1.4-macOS-arm64-py311.dmg`。
- 已核验SHA256：`071343b4abb70492b75c973f41eaf1d2528f9b9c7ea018d22a4f46ae14d27ac0`。
- 运行器：`/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd`。
- FreeCAD：1.1.4，Git提交`4fd3bf320d9566a27e60069fc8387448aaa3a094`。
- OpenCASCADE：7.8.1。
- FreeCAD内置Python：3.11.14；项目主环境仍为Python 3.12.4。

主程序没有把FreeCAD库插入普通虚拟环境。CAD在独立进程中运行，使用JSON任务和文件路径通信；启动CAD时清除主界面的Qt插件变量及Python路径变量，避免环境混用。

`configs/freecad.local.json`是当前可用的本机配置，已被Git忽略。`configs/freecad.example.json`保存同平台可复现的配置示例。`configs/freecad.verified.json`记录运行器哈希、版本、采样数量和最终报告位置。

## 现在怎样使用

在工程work目录中运行：

```bash
./run convert --input data/generated/sphere.stl --target step --unit mm
./run convert --input data/generated/sphere.stl --target igs --unit mm
./run convert --input runs/cad_validation_50k/fixtures/offset_box/source.step --target stl
./run convert --input runs/cad_validation_50k/fixtures/offset_box/source.igs --target stl
./run convert --input runs/cad_validation_50k/fixtures/offset_box/source.step --target igs
./run convert --input runs/cad_validation_50k/fixtures/offset_box/source.igs --target step
```

`./run`自动选择项目虚拟环境和源码。未指定`--config`时自动读取本机配置；需使用其他配置时传入`--config 路径`。`--out`可指定新的任务目录；已有结果不会直接覆盖。每个任务输出HTML、CSV、JSON和模型文件。

STL不自带可靠单位，必须通过`--unit mm/cm/m`明确指定。超过3000面的STL转CAD会拒绝，应先显式生成并评价低面数副本，不能后台偷偷简化。STEP/STP、IGS/IGES扩展名会规范化识别。

主窗口的CAD状态页会显示当前运行器，并提供六向验证报告入口。完整转换现阶段通过命令行执行；图形化文件选择与转换参数面板仍属于后续界面工作。

## 六条路径怎样实现

| 方向 | 处理路线 | 实际回读类型 |
|---|---|---|
| STL→STEP | 网格转CAD面片壳，再写STEP | 本轮为Shell |
| STL→IGS | 网格面片写IGES | 本轮为Compound曲面集合 |
| STEP→STL | CAD形状按明确离散参数生成三角网格 | triangle_mesh |
| IGS→STL | IGES形状读入并离散 | triangle_mesh |
| STEP→IGS | CAD直接交换，必要时处理完整球面的周期接缝 | Compound或Face |
| IGS→STEP | CAD直接交换 | Compound或Shell |

STL转CAD采用明确的surface策略，不把壳体或曲面集合冒充有效实体，不恢复草图和参数化历史。要求solid时当前拒绝，待成员1完整资格检查及实体构造集成后再开放。

CAD互转不经过STL。FreeCAD自身的`isValid`并不足以证明表面正常，因此还检查面积、面数和实际离散是否非空。

## 回读和评价口径

每项任务至少包括独立导出进程、独立细回读进程和独立粗回读进程。进程PID、request_id和模式记录在结果中，旧结果或错配任务不能被当作本次成功。

CAD输入另在新的进程中生成细/粗参考网格。STL输入以缩放到毫米后的原始三角表面为参考。计算点到对方三角表面的双向无向距离；不使用最近顶点近似，不用ICP、自动居中、旋转或缩放掩盖坐标错误。

最终主要配置如下，完整值在报告内冻结：

| 项目 | 配置 |
|---|---:|
| 每方向采样点数 | 50000 |
| 最终随机种子 | 20271018，反向加1 |
| CAD输出网格线性离散 | 0.03 mm |
| 细回读线性离散 | 0.01 mm |
| CAD细参考线性离散 | 0.005 mm |
| 粗回读/粗参考线性离散 | 0.02 mm |
| 包围盒最小/最大坐标允许偏差 | 0.1 mm |
| D95允许值 | 0.1 mm |
| 采样最大偏差允许值 | 0.3 mm |
| 两档评价指标最大差允许值 | 0.02 mm |

这些阈值在测试前配置，修复过程中没有为通过而放宽。D95采用两个方向95分位数的较大值。采样最大偏差是有限采样估计，不是严格连续表面上界。两档离散指标稳定也不是数学误差证明。

转换检查通过的scope是`conversion_roundtrip_sampled_geometry_not_full_mesh_or_clinical_validation`，不等于医学模型完整结构复检通过。成员1的自交、拓扑、保护区域和正式版本服务仍需接入。

## 样本和实际结果

四类几何分别为：非原点长方体、非原点球面、开放平面片、不对称L形体。所有样本均为FreeCAD自生成几何，不是医学病例。各模型保留独立原生STEP、IGS和STL输入；原生CAD互转不会通过STL中间格式。

| 方向 | 测试样本数 | 通过数 |
|---|---:|---:|
| STL→STEP | 4 | 4 |
| STL→IGS | 4 | 4 |
| STEP→STL | 4 | 4 |
| IGS→STL | 4 | 4 |
| STEP→IGS | 4 | 4 |
| IGS→STEP | 4 | 4 |

最终24项中的最大D95约为0.0160295 mm，最大采样偏差约0.0487581 mm，最大包围盒坐标差约0.0146952 mm，最大两档评价差约0.0158205 mm。平面和多面体的接近零结果包含浮点误差，不能将球面结果也写成无损。

厘米单位测试将坐标以厘米表示的长方体STL显式乘10进入毫米CAD内核。回读包围盒约为`[[31,-19,11],[44,-12,15]]`毫米，与预期位置和尺寸一致；没有重复乘10或自动移到原点。

## 真实发现并修复的问题

第一轮记录位于`runs/cad_validation_initial`，21/24项通过，3项球面IGES相关路径失败。失败时IGES文件可读且isValid为true，但完整周期球面导入后的U参数跨度变为0，面积为0，不能生成三角网格。

对这个实际版本的兼容处理是：仅对经面积与参数范围确认的**完整球面**，在IGES导出前沿周期U方向分成两个解析曲面片。没有转成近似网格，也没有重建任意被裁剪的曲面。分割前后面积一致，并由新进程回读和双向距离再验证。结果中记录`iges_export_adaptation`及面积变化。

这个处理会改变面片拓扑表达，因此如实记录Compound/壳体，不宣称实体和设计历史保持。对已经丢失周期范围的旧IGES输入不猜测恢复，明确作为退化CAD拒绝。其他复杂裁剪周期曲面不在该特例修复的覆盖范围内。

第二轮5000点矩阵24/24通过，最终独立种子50000点矩阵也24/24通过；全部记录保留，不删除首轮失败证据。

## 预期失败和拒绝

以下8项结果均符合预期：

1. STL单位未知：拒绝。
2. 超出CAD面数预算：拒绝，不暗中简化。
3. 未获资格的solid请求：拒绝。
4. 非法离散参数：拒绝。
5. 输入输出同格式：拒绝六向转换任务。
6. 强制极短超时：timeout，不显示成功。
7. 损坏STEP：失败并记录原因。
8. 周期参数已退化的旧IGES：失败，不输出零面积假成功。

额外单元测试检查旧request_id回读拒绝、配置校验、同包围盒镜像仍被表面距离发现，以及真实球面IGES回读面积和非空网格。

## 验证和复现

自动测试共36项通过，JUnit位于`runs/verification/pytest_phase2.xml`。真实矩阵独立执行，24个正常转换、8项预期异常和1项厘米单位验证不只依赖单元测试。

复现完整矩阵，选择新的目录：

```bash
.venv/bin/python scripts/validate_cad.py --out runs/cad_validation_repeat
PYTHONPATH=src .venv/bin/python -m pytest -q
```

脚本先保存冻结配置，再创建样本、逐项转换并汇总，存在的结果目录不会覆盖。不同软件版本或平台须重新实测，不能沿用本机验证结论。

为了保证已有网格功能可运行，本轮还处理了本地恢复环境的隐藏文件标记：CLI启动器显式使用本工程源码；PyMeshLab在默认发现不到插件时加载同发行包内已知meshing插件；GUI只修正自身Qt平台插件的Finder隐藏标记并指定对应环境路径。未修改系统Qt设置；FreeCAD运行器与主程序插件环境保持隔离。

## 当前仍不覆盖的内容

本轮完成的是本机六向转换与上述样本的几何回读验证。尚未完成真实医学网格专项实验、自动实体资格确认、任意复杂IGES修复、NX验证、所有平台兼容及完整图形化转换面板。下一步应接入成员1真实诊断与版本服务，再对有来源和单位记录的医学模型开展E6扩展。
