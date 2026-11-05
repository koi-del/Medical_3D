import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from pyvistaqt import QtInteractor
import pyvista as pv


class MeshViewer(QWidget):
    def __init__(self, parent=None, off_screen=False):
        super().__init__(parent)
        self.plotter = QtInteractor(self, shape=(1, 2), off_screen=off_screen, auto_update=False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.context = QLabel("左：输入参考　｜　右：候选 / 回读模型")
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        layout.addWidget(self.plotter.interactor)
        self.plotter.set_background("#eef3f6")
        self.plotter.link_views()
        self.assets = {}
        for index in (0, 1):
            self.plotter.subplot(0, index)
            self.plotter.add_text("Reference" if index == 0 else "Candidate", font_size=11, color="#263b48", name="view_title")
            self.plotter.add_axes()

    @staticmethod
    def polydata(asset):
        return pv.PolyData(asset.vertices.copy(), np.column_stack((np.full(len(asset.faces), 3), asset.faces)).ravel())

    def show_mesh(self, asset, view_id="primary"):
        index = 0 if view_id == "primary" else 1
        self.assets[index] = asset
        self.plotter.subplot(0, index)
        self.plotter.remove_actor("distance_cloud", render=False)
        self.plotter.add_mesh(self.polydata(asset), color="#76a9bc" if index == 0 else "#d9b17f", smooth_shading=False,
                              name="reference_mesh" if index == 0 else "candidate_mesh")
        self.plotter.reset_camera()
        self.plotter.camera.zoom(.85)
        self.plotter.render()

    def show_comparison(self, reference, candidate, details=None):
        self.context.setText(f"左：参考 {reference.version_id[:8]}　｜　右：候选 {candidate.version_id[:8]}　｜　坐标单位：{reference.unit_name or '未知'}")
        if "distance (coord.)" in self.plotter.scalar_bars:
            self.plotter.remove_scalar_bar("distance (coord.)", render=False)
        self.show_mesh(reference)
        self.show_mesh(candidate, "candidate")
        if details is not None:
            limit = max(float(details["distances_ab"].max()), float(details["distances_ba"].max()), 1e-12)
            for index, key in enumerate(("ab", "ba")):
                self.plotter.subplot(0, index)
                stride = max(1, int(np.ceil(len(details["points_"+key])/5000)))
                cloud = pv.PolyData(details["points_"+key][::stride])
                cloud["distance"] = details["distances_"+key][::stride]
                self.plotter.add_mesh(cloud, name="distance_cloud", scalars="distance", clim=(0, limit), cmap="viridis", point_size=5,
                                      render_points_as_spheres=True, scalar_bar_args={"title": "distance (coord.)", "color": "#263b48",
                                          "position_x": .2, "position_y": .015, "width": .6, "height": .06,
                                          "title_font_size": 11, "label_font_size": 10})
        self.plotter.link_views()
        self.plotter.render()

    def highlight_faces(self, version_id, face_ids):
        asset = self.assets.get(0)
        if asset is None or asset.version_id != version_id:
            raise ValueError("高亮索引与当前版本不一致")
        ids = np.asarray(face_ids, dtype=np.int64)
        if len(ids) and (ids.min() < 0 or ids.max() >= len(asset.faces)):
            raise ValueError("invalid face ID")
        self.plotter.subplot(0, 0)
        self.plotter.remove_actor("highlight", render=False)
        self.plotter.add_mesh(self.polydata(asset).extract_cells(ids), color="#df6655", name="highlight", show_edges=True)

    def clear_highlight(self):
        self.plotter.subplot(0, 0)
        self.plotter.remove_actor("highlight")

    def clear_models(self):
        self.context.setText("尚无本次回读预览；完成转换和评价后显示。")
        if "distance (coord.)" in self.plotter.scalar_bars:
            self.plotter.remove_scalar_bar("distance (coord.)", render=False)
        for index in (0, 1):
            self.plotter.subplot(0, index)
            for name in ("reference_mesh", "candidate_mesh", "distance_cloud", "highlight"):
                self.plotter.remove_actor(name, render=False)
        self.assets.clear()
        self.plotter.render()

    def close_viewer(self):
        self.plotter.close()
