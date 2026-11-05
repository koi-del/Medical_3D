from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QSplitter, QFormLayout, QComboBox, QDoubleSpinBox,
    QSpinBox, QFileDialog, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QCheckBox)

from medical_mesh.core.model import load_asset, load_preview, save_asset
from medical_mesh.fixtures import generate_fixtures
from medical_mesh.jobs.qt_manager import JobManager
from .viewer import MeshViewer
from .cad_panel import CadPanel
from .report_viewer import ReportViewer
from .conversion_results import ConversionResults
from .patella_demo import PatellaDemoPanel, PatellaDemoOverview


class MainWindow(QMainWindow):
    def __init__(self, project_dir, off_screen=False):
        super().__init__()
        self.root = Path(project_dir).resolve()
        self.current_asset = None
        self.last_result = None
        self.last_dir = None
        self.pages = {}
        self.current_candidate = None
        self.optimization_result = None
        self.optimization_dir = None
        self.demo_dir = None
        self.demo_reference = self.demo_candidate = None
        self.demo_source_dir = self.root/'data/public/spl_knee/source'
        self.demo_replay = False
        self.setWindowTitle("医学三维模型工作台 · 成员2开发版")
        self.resize(1380, 880)
        central = QWidget()
        layout = QVBoxLayout(central)
        title = QLabel("医学三维模型工作台")
        title.setStyleSheet("font-size:24px;font-weight:600;color:#203c4b;padding:8px")
        layout.addWidget(title)
        info = QLabel("优化 · 双向误差评价 · CAD适配　｜　未接入成员1完整诊断时，候选仅供预览")
        info.setStyleSheet("color:#805526;padding:0 8px 8px")
        layout.addWidget(info)
        bar = QHBoxLayout()
        self.open_button = QPushButton("打开 NPZ / STL / PLY / OBJ")
        self.open_button.clicked.connect(self.open_file)
        self.demo_button = QPushButton("载入合成球面")
        self.demo_button.clicked.connect(self.load_demo)
        self.units = QComboBox(); self.units.addItems(["单位未知", "mm", "cm", "m"])
        bar.addWidget(self.open_button); bar.addWidget(self.demo_button); bar.addWidget(QLabel("STL单位确认")); bar.addWidget(self.units)
        bar.addStretch()
        self.history_button = QPushButton("打开已有任务 / 报告")
        self.history_button.clicked.connect(self.open_saved_task)
        bar.addWidget(self.history_button)
        self.model_label = QLabel("尚未载入模型")
        bar.addWidget(self.model_label)
        layout.addLayout(bar)
        split = QSplitter(Qt.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(300); self.tabs.setMaximumWidth(400)
        self.viewer = MeshViewer(off_screen=off_screen)
        self.workspace = QTabWidget()
        self.workspace.addTab(self.viewer, "模型对比")
        self.conversion_results = ConversionResults()
        self.workspace.addTab(self.conversion_results, "转换结果")
        self.report_viewer = ReportViewer()
        self.workspace.addTab(self.report_viewer, "任务报告")
        self.demo_overview = PatellaDemoOverview()
        self.workspace.addTab(self.demo_overview, "答辩演示总览")
        split.addWidget(self.tabs); split.addWidget(self.workspace)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["候选", "面数", "D95", "采样最大偏差", "判定", "原因"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(180)
        self.table.cellClicked.connect(self.select_candidate)
        layout.addWidget(self.table)
        status_bar = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.cancel_button = QPushButton("取消任务"); self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.jobs.cancel())
        self.report_button = QPushButton("窗口内查看报告"); self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self.open_report)
        self.save_button = QPushButton("保存候选预览包"); self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_candidate)
        status_bar.addWidget(self.status_label, 1); status_bar.addWidget(self.save_button)
        status_bar.addWidget(self.report_button); status_bar.addWidget(self.cancel_button)
        layout.addLayout(status_bar)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(100)
        layout.addWidget(self.log)
        self.setCentralWidget(central)
        self.jobs = JobManager(self)
        self.jobs.progress.connect(lambda stage, message: self.on_progress(stage, message))
        self.jobs.busy_changed.connect(self.on_busy)
        self.jobs.finished.connect(self.on_finished)
        self.jobs.event.connect(self.on_demo_event)
        self._build_pages()
        self.tabs.currentChanged.connect(lambda _: self.table.setVisible(self.tabs.currentWidget() is self.pages["optimization"]))

    def register_page(self, page_id, title, widget):
        if page_id in self.pages:
            raise ValueError("page_id already registered")
        self.pages[page_id] = widget
        self.tabs.addTab(widget, title)

    def show_mesh(self, asset, view_id="primary"):
        self.viewer.show_mesh(asset, view_id)

    def highlight_faces(self, version_id, face_ids):
        self.viewer.highlight_faces(version_id, face_ids)

    def _build_pages(self):
        page = QWidget(); form = QFormLayout(page)
        self.operation = QComboBox(); self.operation.addItems(["qem", "laplacian", "taubin", "remesh"])
        self.ratio = QDoubleSpinBox(); self.ratio.setRange(.05, 1); self.ratio.setSingleStep(.05); self.ratio.setValue(.8)
        self.iterations = QSpinBox(); self.iterations.setRange(0, 20); self.iterations.setValue(5)
        self.edge = QDoubleSpinBox(); self.edge.setRange(.00001, 100000); self.edge.setDecimals(5); self.edge.setValue(1)
        self.samples = QSpinBox(); self.samples.setRange(100, 100000); self.samples.setSingleStep(1000); self.samples.setValue(10000)
        self.search = QCheckBox("九候选搜索（QEM × Taubin）")
        self.run_button = QPushButton("生成候选并复核")
        self.run_button.clicked.connect(self.run_optimization)
        for label, widget in (("操作", self.operation), ("面数保留率", self.ratio), ("平滑/重划分迭代", self.iterations),
                              ("重划分目标边长", self.edge), ("每方向筛选采样", self.samples)):
            form.addRow(label, widget)
        form.addRow(self.search); form.addRow(self.run_button)
        form.addRow(QLabel("最终复核至少50000点，独立种子。\n约束为课程调试值，非医学精度标准。\n正式接受需成员1复检与用户版本提交。"))
        self.register_page("optimization", "优化", page)
        pending = QWidget(); pending_layout = QVBoxLayout(pending)
        pending_layout.addWidget(QLabel("成员1接入区\n\n导入、诊断、修复页面通过register_page注册。\n\n高亮接口必须携带当前version_id。\n\n当前STL导入是成员2的开发预览适配器。"))
        pending_layout.addStretch()
        self.register_page("integration", "诊断接口", pending)
        self.cad = CadPanel(self.root)
        self.cad.requested.connect(self.run_conversion)
        self.register_page("cad", "CAD转换", self.cad)
        self.demo = PatellaDemoPanel(self.root)
        self.demo.run_requested.connect(self.run_patella_demo)
        self.demo.replay_requested.connect(self.replay_patella_demo)
        self.demo.comparison_requested.connect(self.show_demo_comparison)
        self.demo.report_requested.connect(self.open_demo_report)
        self.demo_overview.conversion_requested.connect(self.show_demo_conversion)
        self.demo_overview.conversion_report_requested.connect(lambda direction:self.show_demo_conversion(direction,True))
        self.register_page("patella_demo", "课设演示", self.demo)

    def set_asset(self, asset):
        if self.jobs.busy:
            raise RuntimeError("任务执行中，请等待或取消后切换模型")
        self.current_asset = asset
        self.last_result = None
        self.last_dir = None
        self.current_candidate = None
        self.optimization_result = None
        self.optimization_dir = None
        self.table.setRowCount(0)
        self.save_button.setEnabled(False)
        self.report_button.setEnabled(False)
        self.report_viewer.clear_report()
        self.model_label.setText(f"工作模型：{len(asset.faces):,} 面 · {asset.unit_name or '单位未知'} · {asset.version_id[:8]}")
        self.viewer.show_comparison(asset, asset)
        self.workspace.setCurrentWidget(self.viewer)
        self.cad.set_assets(asset, None)
        self.log.appendPlainText("载入参考版本 " + asset.version_id)

    def load_demo(self):
        directory = self.root / "data/generated"
        if not (directory / "sphere.npz").exists():
            generate_fixtures(directory)
        self.set_asset(load_asset(directory / "sphere.npz"))

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择模型", str(self.root), "Mesh (*.npz *.stl *.ply *.obj)")
        if not path:
            return
        try:
            unit = self.units.currentText() if self.units.currentIndex() else None
            self.set_asset(load_preview(path, unit))
        except Exception as error:
            QMessageBox.warning(self, "无法读取", str(error))

    def run_optimization(self):
        if self.current_asset is None:
            QMessageBox.information(self, "请选择模型", "先载入合成样本或导入模型。")
            return
        self.current_candidate = None
        self.cad.set_assets(self.current_asset, None)
        self.last_result = None
        self.table.setRowCount(0)
        self.save_button.setEnabled(False)
        self.viewer.show_comparison(self.current_asset, self.current_asset)
        directory = self.root / "runs" / (datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid4().hex[:6])
        path = save_asset(self.current_asset, directory / "reference.npz")
        configs = [{"operation": self.operation.currentText(), "keep_ratio": self.ratio.value(),
                    "iterations": self.iterations.value(), "target_edge_length": self.edge.value()}]
        if self.search.isChecked():
            configs = [{"operation": "qem", "keep_ratio": r, "smooth_iterations": n} for r in (.8, .5, .3) for n in (0, 5, 10)]
        request = {"operation": "optimize", "input_path": str(path.resolve()), "output_dir": str(directory.resolve()),
                   "configs": configs, "samples": self.samples.value(), "final_samples": max(50000, self.samples.value())}
        self.last_dir = directory
        self.optimization_dir = directory
        self.report_viewer.clear_report()
        self.workspace.setCurrentWidget(self.viewer)
        self.report_button.setEnabled(False)
        self.jobs.submit(request)

    def run_conversion(self):
        if self.jobs.busy:
            return
        error = self.cad.validation_error()
        if error:
            self.status_label.setText(error)
            return
        try:
            directory = Path(self.cad.output_root.text()).expanduser().resolve() / (datetime.now().strftime("%Y%m%d_%H%M%S")+"_cad_"+uuid4().hex[:6])
            directory.mkdir(parents=True, exist_ok=False)
            request = {"operation": "convert", "target_format": self.cad.target.currentData(),
                       "output_dir": str(directory), "cad_config": {"samples": self.cad.samples.value()}}
            asset = self.cad.selected_asset()
            if self.cad.mode.currentIndex() == 0:
                request.update(input_path=str(Path(self.cad.input_path.text()).expanduser().resolve()),
                               unit=self.cad.units.currentText() if self.cad.units.currentIndex() else None)
            else:
                request["asset_input_path"] = str(save_asset(asset, directory/"source_snapshot.npz"))
            self.last_dir, self.last_result = directory, None
            self.report_button.setEnabled(False)
            self.report_viewer.clear_report(); self.conversion_results.reset()
            self.viewer.clear_models()
            self.workspace.setCurrentWidget(self.conversion_results)
            self.jobs.submit(request, timeout_ms=self.cad.timeout.value()*1000)
        except Exception as error:
            self.status_label.setText("无法启动："+str(error))
            self.log.appendPlainText(str(error))

    def on_progress(self, stage, message):
        self.status_label.setText(message)
        self.log.appendPlainText(f"[{stage}] {message}")

    def on_busy(self, busy):
        for widget in (self.run_button, self.open_button, self.demo_button, self.save_button, self.history_button):
            widget.setEnabled(not busy)
        self.save_button.setEnabled(not busy and self.current_candidate is not None)
        self.cancel_button.setEnabled(busy)
        self.cad.set_busy(busy)
        self.demo.set_busy(busy)

    def on_finished(self, result):
        self.last_result = result
        self.last_dir = Path(result.get("output_dir", self.last_dir))
        self.status_label.setText(f"{result['status']} · {result.get('decision')} · {result.get('quality_status')}")
        self.log.appendPlainText("结果保存于 " + str(self.last_dir))
        self.report_button.setEnabled((self.last_dir / "report.html").exists() and not result.get("report_error"))
        if self.report_button.isEnabled():
            self.report_viewer.load_report(self.last_dir/"report.html")
        if result.get("operation") == "patella_demo":
            self.apply_demo_result(result, replay=False)
            return
        if result.get("operation") == "convert":
            self.status_label.setText(f"CAD：{result['status']} · 几何检查：{result.get('geometry_status', 'not_run')} · 正式网格版本不改变")
            self.conversion_results.display(result)
            self.load_conversion_preview(result)
            self.workspace.setCurrentWidget(self.conversion_results)
            return
        self.optimization_result, self.optimization_dir = result, self.last_dir
        attempts = result.get("attempts", [])
        self.table.setRowCount(len(attempts))
        for row, item in enumerate(attempts):
            m = item.get("final_metrics", item.get("metrics", {}))
            values = [item["candidate_id"], item.get("actual_faces", "—"), m.get("d95", "—"),
                      m.get("sampled_max", "—"), item["decision"], ";".join(item["reason_codes"]) or "未选择"]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(f"{value:.6g}" if isinstance(value, float) else str(value)))
        self.table.resizeColumnsToContents()
        best = result.get("selected_candidate") or result.get("preview_candidate")
        if best:
            for row, item in enumerate(attempts):
                if item["candidate_id"] == best:
                    self.table.selectRow(row); self.select_candidate(row, 0); break

    def select_candidate(self, row, _column):
        if not self.optimization_result or self.jobs.busy or self.current_asset is None:
            return
        attempts = self.optimization_result.get("attempts", [])
        if row >= len(attempts):
            return
        item = attempts[row]
        if not item.get("mesh_path"):
            return
        if self.optimization_result.get("input_version") != self.current_asset.version_id:
            self.log.appendPlainText("拒绝绑定：任务参考版本已失配")
            return
        candidate = load_asset(item["mesh_path"])
        details_path = self.optimization_dir / (item["candidate_id"] + ("_final.npz" if item.get("final_metrics") else "_screening.npz"))
        details = None
        if details_path.exists():
            with np.load(details_path, allow_pickle=False) as arrays:
                details = {k: arrays[k] for k in arrays.files}
        self.current_candidate = candidate
        self.viewer.show_comparison(self.current_asset, candidate, details)
        self.workspace.setCurrentWidget(self.viewer)
        self.cad.set_assets(self.current_asset, candidate)
        self.save_button.setEnabled(True)

    def save_candidate(self):
        if not self.current_candidate:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存候选预览包（不提交正式版本）", "candidate_preview.npz", "NPZ (*.npz)")
        if path:
            save_asset(self.current_candidate, path)
            self.log.appendPlainText("已保存候选预览；参考版本未改变。")

    def open_report(self):
        if self.last_dir:
            self.report_viewer.load_report(self.last_dir/"report.html")
            self.workspace.setCurrentWidget(self.report_viewer)

    def load_conversion_preview(self, result):
        self.viewer.clear_models()
        assets = result.get("preview_assets")
        if not assets:
            return
        try:
            reference, candidate = load_asset(assets["reference"]), load_asset(assets["candidate"])
            with np.load(assets["distances"], allow_pickle=False) as arrays:
                details = {k: arrays[k] for k in arrays.files}
            self.viewer.show_comparison(reference, candidate, details)
            self.viewer.context.setText(f"{(result.get('source_format') or '?').upper()} → {(result.get('target_format') or '?').upper()}　｜　左：输入参考　右：独立回读　｜　距离与坐标：mm")
        except Exception as error:
            self.log.appendPlainText("无法显示转换预览："+str(error))

    def open_saved_task(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开已保存任务或报告", str(self.root/"runs"), "任务报告 (result.json report.html *.html)")
        if path:
            try:
                self.load_saved_task(path)
            except Exception as error:
                self.status_label.setText("打开失败："+str(error))

    def load_saved_task(self, path):
        if self.jobs.busy:
            raise RuntimeError("任务运行中，请等待结束")
        path = Path(path).resolve()
        directory = path.parent
        if not (directory/"report.html").is_file() or path.suffix not in (".json", ".html"):
            raise ValueError("请选择任务目录中的result.json或HTML报告")
        result_path = directory/"result.json"
        if (directory/'demo_result.json').exists() or ((directory/'optimization_summary.json').exists() and (directory/'conversion_summary.json').exists()):
            self.replay_patella_demo(str(directory))
            return
        self.viewer.clear_models()
        if (path.name == "report.html" and result_path.is_file()) or path.name == "result.json":
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError("任务记录格式不正确")
            result["output_dir"] = str(directory)
            # Opening an old optimization never binds its candidate to another reference version.
            self.on_finished(result)
        else:
            self.last_dir = directory
            self.last_result = None
            self.conversion_results.reset()
            self.conversion_results.summary.setText("此文件为汇总报告，请在任务报告页阅读。")
        self.report_viewer.load_report(path if path.suffix == ".html" else directory/"report.html")
        self.workspace.setCurrentWidget(self.report_viewer)
        self.report_button.setEnabled(True)

    def run_patella_demo(self):
        if self.jobs.busy:
            return
        try:
            from medical_mesh.experiments.demo import check_capacity
            if not self.demo.output_root.text().strip():
                raise ValueError('请选择任务保存目录')
            parent=Path(self.demo.output_root.text()).expanduser().resolve()
            check_capacity(parent,self.demo_source_dir,self.demo.keep_samples.isChecked())
            directory=parent/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_patella_demo_'+uuid4().hex[:6])
            self.demo_dir=self.last_dir=directory
            self.demo_reference=self.demo_candidate=None
            self.demo_replay=False;self.last_result=None
            self.demo_overview.reset();self.report_viewer.clear_report();self.viewer.clear_models()
            self.demo.compare_button.setEnabled(False);self.demo.report_button.setEnabled(False)
            self.report_button.setEnabled(False);self.demo.directory.setText(str(directory))
            self.workspace.setCurrentWidget(self.demo_overview)
            request={'operation':'patella_demo','project_dir':str(self.root),'source_dir':str(self.demo_source_dir),
                     'output_dir':str(directory),'keep_all_samples':self.demo.keep_samples.isChecked()}
            self.jobs.submit(request,timeout_ms=self.demo.timeout.value()*60000)
        except Exception as error:
            self.status_label.setText('无法启动演示：'+str(error))

    def on_demo_event(self,event):
        if not self.jobs.request or self.jobs.request.get('operation')!='patella_demo':
            return
        data=event.get('data',{});stage=event['stage']
        self.demo_overview.detail.setText(event['message'])
        if stage=='demo_phase':
            self.demo_overview.phases_update(data['state'].get('phases',{}))
            if data['status']=='completed' and data['phase']=='prepare':
                self.demo_reference=load_asset(self.demo_dir/'reference.npz')
            if data['status']=='completed' and data['phase']=='optimize':
                self.load_demo_optimization()
        elif stage=='optimization_candidate':
            self.demo_overview.candidate_update(data['row'])
        elif stage=='conversion':
            self.demo_overview.conversion_update(data['direction'],stage=data.get('stage','准备'))
        elif stage=='conversion_done':
            path=self.demo_dir/'conversion'/data['direction']/'result.json'
            if path.exists():
                self.demo_overview.conversion_update(data['direction'],json.loads(path.read_text()))

    def load_demo_optimization(self):
        summary=json.loads((self.demo_dir/'optimization_summary.json').read_text())
        for row in summary['rows']:
            self.demo_overview.candidate_update(row)
        name=summary.get('selected')
        if name:
            self.demo_reference=load_asset(self.demo_dir/'reference.npz')
            self.demo_candidate=load_asset(self.demo_dir/'selected_candidate.npz')
            row=next(r for r in summary['rows'] if r['label']==name);metrics=row['final_metrics']
            self.demo_overview.selected.setText(f"最终研究候选：{name} · {row['actual_faces']:,}面 · 减面{100*row['reduction_ratio']:.2f}% · D95 {metrics['d95']:.5f}mm\n三组追加种子通过；候选未提交为正式版本。")
            self.demo.compare_button.setEnabled(True)
            row_index=list(self.demo_overview.rows).index(name)
            self.demo_overview.optimization.selectRow(row_index)
            self.demo_overview.optimization.scrollToItem(self.demo_overview.optimization.item(row_index,0))

    def show_demo_comparison(self):
        if self.demo_reference is None or self.demo_candidate is None:
            return
        summary=json.loads((self.demo_dir/'optimization_summary.json').read_text())
        path=self.demo_dir/'optimization'/summary['selected']/'final_samples.npz'
        details=None
        if path.exists():
            with np.load(path,allow_pickle=False) as arrays:
                details={key:arrays[key] for key in arrays.files}
        self.viewer.show_comparison(self.demo_reference,self.demo_candidate,details)
        self.viewer.context.setText('真实MRI髌骨：左为原始参考，右为优化候选 · mm · 正式工作模型不变')
        self.workspace.setCurrentWidget(self.viewer)

    def show_demo_conversion(self,direction,report=False):
        if not self.demo_dir:
            return
        path=self.demo_dir/'conversion'/direction/'result.json'
        if not path.exists():
            return
        result=json.loads(path.read_text())
        if report:
            self.report_viewer.load_report(path.parent/'report.html')
            self.workspace.setCurrentWidget(self.report_viewer)
        else:
            self.conversion_results.display(result);self.load_conversion_preview(result)
            self.workspace.setCurrentWidget(self.conversion_results)

    def open_demo_report(self):
        if self.demo_dir and (self.demo_dir/'report.html').exists():
            self.report_viewer.load_report(self.demo_dir/'report.html')
            self.workspace.setCurrentWidget(self.report_viewer)

    def apply_demo_result(self,result,replay):
        self.demo_overview.phases_update(result.get('phases',{}))
        status=result.get('status','failed')
        label='历史记录查看 · 未重新计算' if replay else '本次实际重新计算'
        self.demo_overview.mode.setText(label+' · '+('全部几何检查通过' if status=='completed' and result.get('all_geometry_checks_passed') else status))
        elapsed=result.get('elapsed_seconds')
        timing=(f"{'记录' if replay else '本次'}耗时 {elapsed:.1f}秒。" if elapsed is not None else '')
        self.demo_overview.detail.setText('；'.join(result.get('errors',[])) or timing+'可在本窗口查看优化对比、六向回读和总报告。')
        if status=='completed':
            self.load_demo_optimization()
            for path in (self.demo_dir/'conversion').glob('*/result.json'):
                self.demo_overview.conversion_update(path.parent.name,json.loads(path.read_text()))
        self.demo.report_button.setEnabled((self.demo_dir/'report.html').exists())
        try:self.demo.remember(self.demo_dir)
        except OSError as error:self.log.appendPlainText('历史索引写入失败，实验仍可从原目录打开：'+str(error))
        self.demo.refresh_history()
        index=self.demo.history.findData(str(self.demo_dir))
        if index>=0:self.demo.history.setCurrentIndex(index)
        self.status_label.setText(label+' · '+status+' · 候选仍为unverified，正式模型不改变')
        self.workspace.setCurrentWidget(self.demo_overview)

    def replay_patella_demo(self,directory):
        if self.jobs.busy or not directory:
            return
        try:
            path=Path(directory).resolve()
            record=path/'demo_result.json'
            if record.exists():
                result=json.loads(record.read_text())
            else:
                audit=json.loads((path/'artifact_verification.json').read_text())
                result={'operation':'patella_demo','status':'completed' if audit['all_passed'] else 'failed',
                        'all_geometry_checks_passed':audit['all_passed'],
                        'phases':{key:{'status':'completed'} for key in ('prepare','optimize','convert','controls','report')}}
            self.demo_dir=self.last_dir=path;self.demo_replay=True;self.last_result=result
            self.demo_reference=self.demo_candidate=None;self.viewer.clear_models()
            self.demo_overview.reset(replay=True);self.demo.directory.setText(str(path))
            self.demo.compare_button.setEnabled(False)
            self.apply_demo_result(result,replay=True)
            self.report_button.setEnabled((path/'report.html').exists())
            if self.report_button.isEnabled():self.report_viewer.load_report(path/'report.html')
            self.tabs.setCurrentWidget(self.demo)
        except Exception as error:
            self.status_label.setText('无法载入演示记录：'+str(error))

    def closeEvent(self, event):
        if self.jobs.busy:
            self.jobs.cancel()
            self.log.appendPlainText("正在取消任务，结束后可关闭窗口。")
            event.ignore()
            return
        self.viewer.close_viewer()
        super().closeEvent(event)
