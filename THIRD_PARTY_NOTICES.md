# 第三方与数据声明

## 医学网格

BodyParts3D, © The Database Center for Life Science licensed under CC Attribution-Share Alike 2.1 Japan.

- 原始数据库：https://lifesciencedb.jp/bp3d/
- 本次实际下载的 STL 镜像：https://github.com/Kevin-Mattheus-Moerman/BodyParts3D
- 版本：BodyParts3D 3.0 / 20110915，原始 OBJ 经镜像作者转换为二进制 STL。
- 数据许可：CC BY-SA 2.1 Japan；原许可文件保存在 data/medical/LICENSE_content。
- 论文：Mitsuhashi et al., BodyParts3D: 3D structure database for anatomical concepts. Nucleic Acids Res. 2009, https://doi.org/10.1093/nar/gkn613 。
- 模型：FMA7197 肝脏、FMA24474 右股骨、FMA7204 右肾。
- 修改：data/medical 的 STL 保持下载字节不变；results/medical_E1_E2 中派生样本人工加入/移除面或翻面，另记录处理参数和哈希。这些派生网格继续适用原数据许可。
- 来源均为同一个图谱，不代表三个独立受试者。单位未独立核实，软件标为 unknown；不根据形状大小猜测毫米。

## 软件组件

|组件|使用方式|来源与许可概览|
|---|---|---|
|NumPy|数组、面积计算、SVD投影|https://github.com/numpy/numpy ，BSD-3-Clause|
|SciPy|任务二固定边界平滑的稀疏邻接与数值运算|https://github.com/scipy/scipy ，BSD-3-Clause|
|Matplotlib|任务二误差图与HTML报告插图|https://github.com/matplotlib/matplotlib ，许可证随发行包提供|
|FreeCAD（可选外部程序）|STL/STEP/IGS六向写出和独立回读|https://github.com/FreeCAD/FreeCAD ，以外部发行包许可证为准|
|Trimesh|PLY/OBJ辅助读入，关闭 process|https://github.com/mikedh/trimesh ，MIT|
|PyMeshLab|复用自交选择过滤器|https://github.com/cnr-isti-vclab/PyMeshLab ，GPL-3.0|
|PyVista / PyVistaQt|显示副本与Qt视图|https://github.com/pyvista/pyvista 、https://github.com/pyvista/pyvistaqt ，MIT|
|VTK|PyVista底层渲染|https://github.com/Kitware/VTK ，BSD风格许可|
|PySide6|Qt界面与QProcess|https://doc.qt.io/qtforpython-6/ ，LGPLv3/GPLv3/商业许可，按所用模块核对|
|pytest|开发验证|https://github.com/pytest-dev/pytest ，MIT|

自主实现：STL编解码与严格校验、精确坐标焊接、边面邻接、重复与退化面、边界环、顶点link/扇区检查、方向冲突、连通分量、投影耳切补洞、法线一致化、候选保护与回退、版本快照、任务协议及页面控制。

自交接口参考官方过滤器文档：https://pymeshlab.readthedocs.io/en/latest/filter_list.html#compute-selection-by-self-intersections-per-face 。未复制第三方实现源码。本项目课程提交以源码形式交付，含 GPL 组件的整体发行需按适用条款组织，不将整体简单标为 MIT；本文件保留组件来源，依赖自身的完整许可随所安装发行包提供。
