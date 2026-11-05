import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView


class ConversionResults(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary = QLabel("选择CAD转换页开始任务，或打开已保存的任务。")
        self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.stages = QLabel(); self.stages.setWordWrap(True); layout.addWidget(self.stages)
        self.paths = QLabel(); self.paths.setWordWrap(True); layout.addWidget(self.paths)
        self.metrics = QTableWidget(0, 3)
        self.metrics.setHorizontalHeaderLabels(["项目", "本次结果", "通过标准 / 说明"])
        self.metrics.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.metrics.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.metrics, 1)
        self.scope = QLabel("几何检查只覆盖有限采样与本机FreeCAD回读；完整网格诊断、医学合格和第三方CAD兼容性需另行验证。")
        self.scope.setWordWrap(True); layout.addWidget(self.scope)
        self.result = None

    def reset(self):
        self.result = None
        self.summary.setText("正在转换；本次结果尚未生成。")
        self.stages.clear(); self.paths.clear(); self.metrics.setRowCount(0)

    def display(self, result):
        self.result = result
        fmt = lambda name: (result.get(name) or "?").upper()
        status = result.get("status")
        passed = status == "completed" and result.get("geometry_status") == "passed"
        self.summary.setText(f"{fmt('source_format')} → {fmt('target_format')}　{'几何验证通过' if passed else '未通过 / 未完成'}　· {status}\n" + "；".join(result.get("errors", []) + result.get("reason_codes", [])))
        self.summary.setStyleSheet("font-size:17px;color:" + ("#216342" if passed else "#a13a24"))
        self.stages.setText(f"文件写出：{result.get('export_status', 'not_run')}　｜　回读：{result.get('readback_status', 'not_run')}　｜　几何：{result.get('geometry_status', 'not_run')}\n实际表示：{result.get('actual_representation', '未获得')} · 距离单位：mm · 用时 {result.get('elapsed_seconds', 0):.2f}秒")
        self.paths.setText(f"输入：{result.get('input_path', '—')}\n输出：{result.get('output_path', '未生成')}\n任务：{result.get('output_dir', '—')}")
        metrics, config = result.get("metrics", {}), result.get("config", {})
        rows = [("ASD / mm", metrics.get("asd"), "双向平均表面偏差"),
                ("D95 / mm", metrics.get("d95"), f"≤ {config.get('d95_mm', '—')}"),
                ("采样最大偏差 / mm", metrics.get("sampled_max"), f"≤ {config.get('sampled_max_mm', '—')}"),
                ("包围盒最大差 / mm", result.get("bbox_max_delta_mm"), f"≤ {config.get('coordinate_tolerance_mm', '—')}"),
                ("两档离散误差差 / mm", result.get("convergence_delta_mm"), f"≤ {config.get('convergence_tolerance_mm', '—')}"),
                ("每方向采样点数", config.get("samples"), "有限采样估计，不是精确Hausdorff距离"),
                ("单位变换", json.dumps(result.get("unit_transform", {}), ensure_ascii=False), "CAD按文件单位读取；网格单位显式确认")]
        names = {"coordinate_bbox":"坐标和尺寸", "d95":"D95阈值", "sampled_max":"采样最大偏差阈值",
                 "tessellation_stability":"两档离散稳定性", "independent_readback_process":"独立回读进程",
                 "valid_cad_readback":"回读形状有效性"}
        rows += [(names.get(name, name), "通过" if value else "失败", "独立检查") for name, value in result.get("checks", {}).items()]
        if result.get("source_asset"):
            rows.append(("网格来源", result["source_asset"]["version_id"], "仅转换副本，正式版本不改变"))
        self.metrics.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.metrics.setItem(r, c, QTableWidgetItem("未执行" if value is None else f"{value:.8g}" if isinstance(value, float) else str(value)))
        self.metrics.resizeRowsToContents()
