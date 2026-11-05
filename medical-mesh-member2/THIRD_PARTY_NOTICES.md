# 第三方组件和来源

本工程调用安装环境内的组件，没有把第三方算法源文件复制进项目。版本以平台锁文件及每次result.json环境记录为准。分发时应保留相应发行包的许可证和声明；本文件仅记录使用来源。

| 组件 | 用途 | 官方来源 |
|---|---|---|
| NumPy/SciPy | 数值、采样与稀疏邻接 | https://github.com/numpy/numpy · https://github.com/scipy/scipy |
| PyMeshLab | QEM和各向同性重划分 | https://github.com/cnr-isti-vclab/PyMeshLab |
| VTK | 点到三角单元的最近表面查询 | https://github.com/Kitware/VTK |
| Trimesh | 合成样本、开发预览读取和STL导出 | https://github.com/mikedh/trimesh |
| PyVista/PyVistaQt | Qt内三维显示 | https://github.com/pyvista/pyvista · https://github.com/pyvista/pyvistaqt |
| PySide6-Essentials | Qt窗口与进程事件 | https://doc.qt.io/qtforpython-6/ |
| Matplotlib | 双向误差报告图 | https://github.com/matplotlib/matplotlib |
| pytest | 几何和故障测试 | https://docs.pytest.org/ |
| FreeCAD | 外部CAD适配，本机已安装并验证1.1.4 | https://github.com/FreeCAD/FreeCAD |

算法背景：QEM参考https://www.cs.cmu.edu/~garland/quadrics/；Taubin参考1995年A Signal Processing Approach to Fair Surface Design。固定边界均匀平滑、评价组合、候选策略、协议、UI和报告逻辑由本工程实现，不称为重新发明底层算法。

2026年10月18日核对的接口：

- https://pymeshlab.readthedocs.io/en/latest/filter_list.html
- https://vtk.org/doc/nightly/html/classvtkStaticCellLocator.html
- https://qt.pyvista.org/api_reference.html
- https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/MeshPart/App/AppMeshPartPy.cpp

FreeCAD接口网页核对不代表目标机器六向转换运行通过。实际运行验证见phase2_freecad、phase3_desktop和runs记录。

2026年10月22日新增公开医学数据实验：SPL Knee Atlas髌骨模型。作者Jen Richolt、Marianna Jakab、Ron Kikinis；Surgical Planning Laboratory / Brigham and Women's Hospital / Harvard Medical School。数据遵循官方指定的3D Slicer License section B；实验目录保留完整许可证、源通知、署名和修改说明。数据许可独立于本工程与第三方代码许可。来源：https://www.openanatomy.org/atlas-pages/atlas-spl-knee.html 。
