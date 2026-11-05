# SPL Knee Atlas公开MRI模型来源

来源：https://www.openanatomy.org/atlas-pages/atlas-spl-knee.html

官方ZIP：https://www.openanatomy.org/atlases/nac/knee-2016-09.zip

作者：Jen Richolt、Marianna Jakab、Ron Kikinis；Surgical Planning Laboratory / Brigham and Women's Hospital / Harvard Medical School。

许可：官方指定3D Slicer License section B。原始通知与完整许可已下载保存在本机`source/`与实验输出目录。使用数据时保留许可、署名和修改说明。

下载时间：2026-10-22。使用的结构：`Data/Model_98_patella.vtk`。年龄、采集日期和左右侧未做断言。旧Slicer场景物理坐标按官方毫米约定解释；数值位置保留，解剖RAS方向仅依据旧场景推定，未独立检查DICOM方向。

原始ZIP SHA256：`2f61002f42843910eada3877adf4229ef845bf87cc1e422b719c930dfadc5f6a`。

原始VTK SHA256：`592fdfbb7dda4b1a9fe89a5c2d3cc1b5eacfed12490eceda92c3d1d0958ede76`。

运行`PYTHONPATH=src .venv/bin/python scripts/experiments/medical_patella.py --phase all --out runs/你的新目录`可提取源模型、执行优化及六向转换并生成报告。`source/`是忽略版本控制的缓存；完整数据与许可仍保存在本机，首次复现会下载约77MiB。

最终实验在`runs/medical_patella_verified_20261022/`；初选1,798面被独立复测淘汰的记录在`runs/medical_patella_20261022/`；最初重复坐标索引未规范化的诊断记录在`runs/medical_patella_initial_20261022/`。不能把这两个历史目录当作最终交付。
