"""CAD job form; creates requests only after explicit source/unit validation."""
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QFileDialog, QSpinBox, QScrollArea)
from medical_mesh.cad.runner import FORMATS, effective_config, probe_freecad


class CadPanel(QWidget):
    requested = Signal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.asset = self.candidate = None
        self.busy = False
        outer = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); form = QFormLayout(content)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.mode = QComboBox(); self.mode.addItems(["外部文件", "当前参考网格", "所选优化候选（预览）"])
        form.addRow("输入来源", self.mode)
        self.input_path = QLineEdit(); self.input_path.setPlaceholderText("STL / STEP / STP / IGS / IGES")
        self.browse = QPushButton("选择文件…")
        row = QHBoxLayout(); row.addWidget(self.input_path, 1); row.addWidget(self.browse)
        form.addRow("输入文件", row)
        self.source_label = QLabel(); self.source_label.setWordWrap(True); form.addRow(self.source_label)
        self.target = QComboBox(); form.addRow("输出格式", self.target)
        self.units = QComboBox(); self.units.addItems(["请选择STL单位", "mm", "cm", "m"])
        form.addRow("STL单位（必须确认）", self.units)
        self.output_root = QLineEdit(str(self.root/"runs"))
        self.output_browse = QPushButton("任务保存位置…")
        form.addRow("任务保存目录", self.output_root); form.addRow(self.output_browse)
        self.samples = QSpinBox(); self.samples.setRange(1000, 100000); self.samples.setSingleStep(1000)
        self.samples.setValue(effective_config()["samples"])
        form.addRow("每方向采样点数", self.samples)
        self.timeout = QSpinBox(); self.timeout.setRange(10, 3600); self.timeout.setValue(300); self.timeout.setSuffix(" 秒")
        form.addRow("整项任务超时", self.timeout)
        self.validation = QLabel(); self.validation.setWordWrap(True); form.addRow(self.validation)
        self.run_button = QPushButton("转换并回读验证"); self.run_button.setMinimumHeight(38)
        form.addRow(self.run_button)
        self.runtime = probe_freecad()
        runtime_label = QLabel("FreeCAD：" + ("已配置\n" + self.runtime["executable"] if self.runtime["status"] == "configured" else "不可用"))
        runtime_label.setWordWrap(True); form.addRow(runtime_label)
        help_label = QLabel("STL ↔ STEP ↔ IGS，共六个方向。\nSTL转CAD限3000面，输出按曲面处理。\n通过：写出 → 独立回读 → 双向几何检查。\n距离单位统一为mm。CAD参考采用细离散近似。\n转换通过不代表网格修复或医学合格。")
        help_label.setWordWrap(True); form.addRow(help_label)
        scroll.setWidget(content); outer.addWidget(scroll)
        self.browse.clicked.connect(self.choose_file)
        self.output_browse.clicked.connect(self.choose_output)
        self.run_button.clicked.connect(self.requested)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.input_path.textChanged.connect(self.input_changed)
        self.units.currentIndexChanged.connect(self.refresh)
        self.output_root.textChanged.connect(self.refresh)
        self.refresh()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择CAD或STL输入", str(self.root), "CAD / Mesh (*.stl *.step *.stp *.igs *.iges)")
        if path:
            self.input_path.setText(path)

    def input_changed(self):
        # A different STL needs its own explicit unit acknowledgement.
        self.units.setCurrentIndex(0)
        self.refresh()

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出根目录", self.output_root.text())
        if path:
            self.output_root.setText(path)

    def selected_asset(self):
        return self.asset if self.mode.currentIndex() == 1 else self.candidate if self.mode.currentIndex() == 2 else None

    def set_assets(self, asset, candidate):
        self.asset, self.candidate = asset, candidate
        self.refresh()

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.mode, self.target, self.units, self.output_root, self.output_browse, self.samples, self.timeout):
            widget.setEnabled(not busy)
        self.refresh()

    def refresh(self):
        file_mode = self.mode.currentIndex() == 0
        self.input_path.setEnabled(file_mode and not self.busy); self.browse.setEnabled(file_mode and not self.busy)
        asset = self.selected_asset()
        fmt = FORMATS.get(Path(self.input_path.text()).suffix.lower().lstrip(".")) if file_mode else "stl"
        targets = [x for x in ("stl", "step", "igs") if x != fmt]
        previous = self.target.currentData()
        if [self.target.itemData(i) for i in range(self.target.count())] != targets:
            self.target.clear()
            for target in targets:
                self.target.addItem(target.upper(), target)
            if previous in targets:
                self.target.setCurrentIndex(targets.index(previous))
        self.units.setEnabled(file_mode and fmt == "stl" and not self.busy)
        if file_mode:
            self.source_label.setText("来源格式：" + (fmt.upper() if fmt else "未识别") + (" · 按CAD文件内单位读取" if fmt in ("step", "igs") else ""))
        else:
            self.source_label.setText((f"{len(asset.faces):,}面 · {asset.unit_name or '单位未知'}\n版本 {asset.version_id[:8]} · 保留原版本" if asset else "请先载入网格或生成并选择候选。"))
        error = self.validation_error()
        self.validation.setText(error or "输入有效；将在独立进程转换和验证。")
        self.validation.setStyleSheet("color:#a13a24" if error else "color:#286849")
        self.run_button.setEnabled(not error and not self.busy)

    def validation_error(self):
        if self.runtime["status"] != "configured":
            return "未找到FreeCAD，请配置运行环境。"
        if not self.output_root.text().strip():
            return "请填写任务保存目录。"
        destination = Path(self.output_root.text()).expanduser()
        if destination.exists() and not destination.is_dir():
            return "任务保存位置必须是文件夹。"
        if self.mode.currentIndex() == 0:
            path = Path(self.input_path.text()).expanduser()
            fmt = FORMATS.get(path.suffix.lower().lstrip("."))
            if not path.is_file() or not fmt:
                return "请选择存在的STL、STEP或IGS文件。"
            if fmt == "stl" and self.units.currentIndex() == 0:
                return "STL不记录单位：请先确认输入单位。"
        else:
            asset = self.selected_asset()
            if asset is None:
                return "没有可转换的参考网格或候选。"
            if asset.unit_status != "confirmed":
                return "网格单位未确认，不能进行CAD转换。"
            if len(asset.faces) > effective_config()["max_stl_faces"]:
                return "超过3000面预算，请先优化并选择经过评价的简化候选。"
        return None
