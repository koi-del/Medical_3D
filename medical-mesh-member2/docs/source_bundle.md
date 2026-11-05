# 完整源码包安装与复现说明

打包日期：2026-10-23。解压后的 `medical-mesh-member2` 为项目根目录，以下命令均在该目录执行。

## 包内内容

- `src/medical_mesh/`：完整业务代码，包括模型交接、网格优化、误差评价、FreeCAD转换、后台任务、桌面界面、真实髌骨实验和报告。
- `scripts/`、`tests/`：命令行实验、GUI验收、故障测试和源码打包脚本。
- `configs/`：评价阈值、优化约束、FreeCAD配置模板及本机历史验证参数。
- `docs/`：接口约定、各阶段说明、答辩操作说明；`docs/plans/`另附此前两份完整实施方案。
- `data/public/spl_knee/source/`：原始图谱ZIP、髌骨VTK、场景、来源页面和许可证。缓存齐全时，医学实验的数据准备无需再次联网下载。Python软件依赖安装通常仍需网络。
- `requirements.in`、平台依赖锁、`pyproject.toml`、两个macOS启动器及 `run`。
- `BUNDLE_MANIFEST.json`：包内文件的大小与SHA256，可校验完整性。

不包含本机 `.venv`、FreeCAD应用程序、Git历史、缓存和旧 `runs/`。这些均非项目源码；历史报告路径出现在原有文档中时，代表原机器实验记录，源码包不会包含对应目录。重新运行会生成新的 `runs/`。已有课设实验报告另有交付包。

## 1. 安装Python依赖

已实测平台为macOS Apple Silicon、Python 3.12.4、FreeCAD 1.1.4。建议先在相同平台复现。Windows和Linux需自行安装对应发行包；Windows进程树取消行为尚未完成验证。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pip check
```

`requirements-lock-macos-arm64-py312.txt`记录原机器依赖版本，需要严格复现同平台时，可在安装项目之前使用：

```bash
.venv/bin/python -m pip install -r requirements-lock-macos-arm64-py312.txt
.venv/bin/python -m pip install --no-deps -e .
```

其他平台优先使用 `pyproject.toml` 安装，不直接套用包含macOS专用包的锁文件。Windows命令中的Python路径替换为 `.venv\Scripts\python.exe`，创建环境可使用 `py -3.12 -m venv .venv`。

## 2. 安装并配置FreeCAD

从FreeCAD官方发行页安装应用：https://github.com/FreeCAD/FreeCAD/releases 。本工程既有验证版本为1.1.4，Python主程序通过独立FreeCAD进程执行转换，无需在项目虚拟环境中直接导入FreeCAD。

```bash
cp configs/freecad.example.json configs/freecad.local.json
```

编辑 `configs/freecad.local.json` 的 `executable`，指向实际的命令行运行器。macOS已验证路径为：

```text
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd
```

Windows/Linux应填写目标安装版本真实存在的命令行运行器路径；JSON中的Windows反斜线需写为 `\\`，或使用 `/`。保留 `arguments: ["{script}"]` 及其余阈值。本地配置故意不随包复制，以免把原电脑绝对路径当成新电脑配置。

## 3. 启动整个演示

```bash
chmod +x run 启动医学网格工作台.command 启动髌骨答辩演示.command
./启动髌骨答辩演示.command
```

进入“课设演示”后，点击“一键重新运行完整实验”。默认答辩模式仍执行真实计算：原始数据准备→十组优化→独立种子复核→STL/STEP/IGS六向转换与回读→负对照→图文报告。完成后在窗口内查看模型对比、六向结果和总报告。首次解压没有历史记录是正常情况。

跨平台或终端启动可用：

```bash
PYTHONPATH=src .venv/bin/python -m medical_mesh.app --project-dir . --patella-demo
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m medical_mesh.app --project-dir . --patella-demo
```

默认答辩模式约81MiB输出，启动前至少要求160MiB可用空间；完整中间采样模式至少要求512MiB。依赖和FreeCAD安装另需空间。本机此前完整演示约一分钟，实际耗时随电脑变化。

## 4. 验证安装和复现实验

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python scripts/gui_smoke.py
PYTHONPATH=src .venv/bin/python scripts/gui_cad_smoke.py
PYTHONPATH=src .venv/bin/python scripts/gui_patella_demo_smoke.py
```

GUI测试需要可用桌面会话；后两项需要配置FreeCAD，完整GUI测试会生成多次任务与对应产物。不是只安装Python依赖就能执行所有CAD测试。

命令行复现真实医学实验：

```bash
PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase all --out runs/patella_reproduction
```

必须指定尚未使用过的输出目录，避免覆盖实验。默认历史研究脚本会保留更完整的实验产物；答辩按钮会使用独立新目录并生成窗口内报告。

## 5. 数据和实验边界

SPL Knee Atlas作者：Jen Richolt、Marianna Jakab、Ron Kikinis；Surgical Planning Laboratory / Brigham and Women's Hospital / Harvard Medical School。来源：https://www.openanatomy.org/atlas-pages/atlas-spl-knee.html 。保留 `source/LICENSE.md` 与完整 `3D-Slicer-License.txt`，数据许可独立于项目代码及依赖软件。

原始ZIP SHA256：`2f61002f42843910eada3877adf4229ef845bf87cc1e422b719c930dfadc5f6a`。

原始VTK SHA256：`592fdfbb7dda4b1a9fe89a5c2d3cc1b5eacfed12490eceda92c3d1d0958ede76`。

项目是成员2课程实验原型：成员1正式诊断及版本服务仍待接入。转换几何检查通过不代表有效实体或临床适用；局部转换误差很小不等于解剖重建精度。更详细的技术和答辩说明见 `README.md`、`docs/phase5_patella_demo.md` 及此前实施方案。

## 6. 再次生成源码包

```bash
PYTHONPATH=src .venv/bin/python scripts/package_source.py --output ../outputs/医学三维模型工作台_成员2_完整源码.zip
```

脚本采用明确的源码目录清单，排除环境、历史运行产物及本地配置，保留启动脚本的可执行位，并逐文件校验ZIP中的SHA256。
