from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QSplitter, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QCheckBox,QGroupBox
from medical_mesh.member2.core.model import load_asset, load_preview, save_asset
from medical_mesh.member2.jobs.qt_manager import JobManager
from .viewer import MeshViewer
from .cad_panel import CadPanel
from .report_viewer import ReportViewer
from .conversion_results import ConversionResults

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
        self.setWindowTitle('医学三维模型工作台 · 成员2开发版')
        self.resize(1380, 880)
        central = QWidget()
        layout = QVBoxLayout(central)
        title = QLabel('医学三维模型工作台')
        title.setStyleSheet('font-size:24px;font-weight:600;color:#203c4b;padding:8px')
        layout.addWidget(title)
        info = QLabel('优化 · 双向误差评价 · CAD适配 ｜ 候选接入统一诊断与版本审核，接受前不改变正式版本')
        info.setStyleSheet('color:#805526;padding:0 8px 8px')
        layout.addWidget(info)
        bar = QHBoxLayout()
        self.open_button = QPushButton('打开 NPZ / STL / PLY / OBJ')
        self.open_button.clicked.connect(self.open_file)
        self.units = QComboBox()
        self.units.addItems(['单位未知', 'mm', 'cm', 'm'])
        bar.addWidget(self.open_button)
        self.unit_label=QLabel('STL单位确认');bar.addWidget(self.unit_label)
        bar.addWidget(self.units)
        bar.addStretch()
        self.history_button = QPushButton('打开已有任务 / 报告')
        self.history_button.clicked.connect(self.open_saved_task)
        bar.addWidget(self.history_button)
        self.model_label = QLabel('尚未载入模型')
        bar.addWidget(self.model_label)
        layout.addLayout(bar)
        split = QSplitter(Qt.Horizontal)
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(300)
        self.tabs.setMaximumWidth(400)
        self.viewer = MeshViewer(off_screen=off_screen)
        self.workspace = QTabWidget()
        self.workspace.addTab(self.viewer, '模型对比')
        self.conversion_results = ConversionResults()
        self.workspace.addTab(self.conversion_results, '转换结果')
        self.report_viewer = ReportViewer()
        self.workspace.addTab(self.report_viewer, '任务报告')
        split.addWidget(self.tabs)
        split.addWidget(self.workspace)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['候选', '面数', 'D95', '采样最大偏差', '判定', '原因'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(180)
        self.table.cellClicked.connect(self.select_candidate)
        layout.addWidget(self.table)
        status_bar = QHBoxLayout()
        self.status_label = QLabel('就绪')
        self.cancel_button = QPushButton('取消任务')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(lambda: self.jobs.cancel())
        self.report_button = QPushButton('窗口内查看报告')
        self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self.open_report)
        self.save_button = QPushButton('保存候选预览包')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_candidate)
        status_bar.addWidget(self.status_label, 1)
        status_bar.addWidget(self.save_button)
        status_bar.addWidget(self.report_button)
        status_bar.addWidget(self.cancel_button)
        layout.addLayout(status_bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        layout.addWidget(self.log)
        self.setCentralWidget(central)
        self.jobs = JobManager(self)
        self.jobs.progress.connect(lambda stage, message: self.on_progress(stage, message))
        self.jobs.busy_changed.connect(self.on_busy)
        self.jobs.finished.connect(self.on_finished)
        self._build_pages()
        self.tabs.currentChanged.connect(lambda _: self.table.setVisible(self.tabs.currentWidget() is self.pages['optimization']))

    def register_page(self, page_id, title, widget):
        if page_id in self.pages:
            raise ValueError('page_id already registered')
        self.pages[page_id] = widget
        self.tabs.addTab(widget, title)

    def show_mesh(self, asset, view_id='primary'):
        self.viewer.show_mesh(asset, view_id)

    def highlight_faces(self, version_id, face_ids):
        self.viewer.highlight_faces(version_id, face_ids)

    def _build_pages(self):
        page = QWidget()
        form = QFormLayout(page);self.optimization_form=form
        self.operation = QComboBox()
        for label,key in [('网格简化（QEM）','qem'),('平滑（Laplacian，可能收缩）','laplacian'),('平滑（Taubin，减少收缩）','taubin'),('重划分（均匀三角网格）','remesh')]:self.operation.addItem(label,key)
        self.target_mode=QComboBox();self.target_mode.addItems(['保留百分比','目标三角面数'])
        self.target_faces=QSpinBox();self.target_faces.setRange(4,10000000);self.target_faces.setValue(3000)
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(1,100);self.ratio.setSuffix(' %');self.ratio.setSingleStep(5);self.ratio.setValue(80)
        self.target_hint=QLabel('导入后显示预计目标面数');self.target_hint.setWordWrap(True)
        self.refine_quality=QCheckBox('质量增强（原表面投影，最多3轮）');self.refine_quality.setChecked(True)
        self.iterations = QSpinBox()
        self.iterations.setRange(0, 20)
        self.iterations.setValue(5)
        self.edge = QDoubleSpinBox()
        self.edge.setRange(1e-05, 100000)
        self.edge.setDecimals(5)
        self.edge.setValue(1)
        self.samples = QSpinBox()
        self.samples.setRange(100, 100000)
        self.samples.setSingleStep(1000)
        self.samples.setValue(10000)
        self.search = QCheckBox('九候选搜索（QEM × Taubin）')
        self.run_button = QPushButton('生成候选并复核')
        self.run_button.clicked.connect(self.run_optimization)
        for label, widget in (('操作', self.operation),('简化目标',self.target_mode),('保留比例',self.ratio),('目标面数',self.target_faces),
                              ('预计结果',self.target_hint),('平滑/重划分迭代', self.iterations), ('重划分目标边长', self.edge)):
            form.addRow(label, widget)
        form.addRow(self.search)
        form.addRow(self.refine_quality)
        self.advanced=QGroupBox('高级：采样与误差阈值（勾选展开）');self.advanced.setCheckable(True);self.advanced.setChecked(False)
        advanced_layout=QVBoxLayout(self.advanced);self.advanced_content=QWidget();advanced_form=QFormLayout(self.advanced_content)
        advanced_form.addRow('每方向筛选采样',self.samples)
        self.limit_d95=QDoubleSpinBox();self.limit_max=QDoubleSpinBox();self.limit_area=QDoubleSpinBox()
        for widget,value,label in ((self.limit_d95,.001,'D95 / 包围盒对角线'),(self.limit_max,.003,'最大采样偏差 / 对角线'),(self.limit_area,.01,'面积相对变化')):
            widget.setDecimals(6);widget.setRange(0,1);widget.setSingleStep(.001);widget.setValue(value);advanced_form.addRow(label,widget)
        advanced_layout.addWidget(self.advanced_content);self.advanced_content.hide()
        self.advanced.toggled.connect(self.advanced_content.setVisible);form.addRow(self.advanced)
        form.addRow(self.run_button)
        note=QLabel('天然开口、分量与自交均会复检。\n最终每方向至少50,000点、独立种子。\n生成方案后预览，点击接受才替换当前模型。');note.setWordWrap(True);form.addRow(note)
        for signal in (self.operation.currentIndexChanged,self.target_mode.currentIndexChanged,self.ratio.valueChanged,self.target_faces.valueChanged):signal.connect(self.refresh_parameters)
        self.register_page('optimization', '优化', page)
        self.cad = CadPanel(self.root)
        self.cad.requested.connect(self.run_conversion)
        self.register_page('cad', 'CAD转换', self.cad)
        self.refresh_parameters()

    def refresh_parameters(self,*_):
        operation=self.operation.currentData();simplify=operation=='qem';count_mode=self.target_mode.currentIndex()==1
        busy=bool(getattr(self,'jobs',None) and self.jobs.busy)
        self.target_mode.setEnabled(simplify and not busy);self.ratio.setEnabled(simplify and not count_mode and not busy)
        self.target_faces.setEnabled(simplify and count_mode and not busy)
        self.edge.setEnabled(operation=='remesh' and not busy);self.iterations.setEnabled(operation!='qem' and not busy)
        for widget,visible in ((self.target_mode,simplify),(self.ratio,simplify and not count_mode),
                (self.target_faces,simplify and count_mode),(self.target_hint,simplify),
                (self.iterations,not simplify),(self.edge,operation=='remesh'),(self.search,simplify),(self.refine_quality,operation=='remesh')):
            self.optimization_form.setRowVisible(widget,visible)
        if self.current_asset:
            n=len(self.current_asset.faces);target=min(n,self.target_faces.value()) if count_mode else max(4,int(n*self.ratio.value()/100))
            self.target_hint.setText(f'当前 {n:,} 面 → 目标 {target:,} 面；实际结果由复检记录确认。')

    def set_asset(self, asset):
        if self.jobs.busy:
            raise RuntimeError('任务执行中，请等待或取消后切换模型')
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
        self.target_faces.setMaximum(max(4,len(asset.faces)));self.refresh_parameters()
        self.log.appendPlainText('载入参考版本 ' + asset.version_id)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择模型', str(self.root), 'Mesh (*.npz *.stl *.ply *.obj)')
        if not path:
            return
        try:
            unit = self.units.currentText() if self.units.currentIndex() else None
            self.set_asset(load_preview(path, unit))
        except Exception as error:
            QMessageBox.warning(self, '无法读取', str(error))

    def run_optimization(self):
        if self.current_asset is None:
            QMessageBox.information(self, '请选择模型', '请先到“导入、诊断与修复”页导入模型。')
            return
        self.current_candidate = None
        self.cad.set_assets(self.current_asset, None)
        self.last_result = None
        self.table.setRowCount(0)
        self.save_button.setEnabled(False)
        self.viewer.show_comparison(self.current_asset, self.current_asset)
        directory = self.root / 'runs' / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:6])
        path = save_asset(self.current_asset, directory / 'reference.npz')
        configs = [{'operation': self.operation.currentData(), 'keep_ratio': self.ratio.value()/100, 'iterations': self.iterations.value(), 'target_edge_length': self.edge.value()}]
        if self.operation.currentData()=='qem' and self.target_mode.currentIndex()==1:configs[0]['target_faces']=self.target_faces.value()
        configs[0]['quality_refinement']=self.refine_quality.isChecked()
        if self.search.isChecked():
            configs = [{'operation': 'qem', 'keep_ratio': r, 'smooth_iterations': n} for r in (0.8, 0.5, 0.3) for n in (0, 5, 10)]
        request = {'operation': 'optimize', 'input_path': str(path.resolve()), 'output_dir': str(directory.resolve()), 'configs': configs, 'samples': self.samples.value(), 'final_samples': max(50000, self.samples.value())}
        request['provider']=getattr(self,'diagnostic_provider',None)
        request['limits']={'d95_normalized':self.limit_d95.value(),'sampled_max_normalized':self.limit_max.value(),'area_change':self.limit_area.value()}
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
            directory = Path(self.cad.output_root.text()).expanduser().resolve() / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_cad_' + uuid4().hex[:6])
            directory.mkdir(parents=True, exist_ok=False)
            request = {'operation': 'convert', 'target_format': self.cad.target.currentData(), 'output_dir': str(directory), 'cad_config': {'samples': self.cad.samples.value()}}
            asset = self.cad.selected_asset()
            if self.cad.mode.currentIndex() == 0:
                request.update(input_path=str(Path(self.cad.input_path.text()).expanduser().resolve()), unit=self.cad.units.currentText() if self.cad.units.currentIndex() else None)
            else:
                request['asset_input_path'] = str(save_asset(asset, directory / 'source_snapshot.npz'))
            self.last_dir, self.last_result = (directory, None)
            self.report_button.setEnabled(False)
            self.report_viewer.clear_report()
            self.conversion_results.reset()
            self.viewer.clear_models()
            self.workspace.setCurrentWidget(self.conversion_results)
            self.jobs.submit(request, timeout_ms=self.cad.timeout.value() * 1000)
        except Exception as error:
            self.status_label.setText('无法启动：' + str(error))
            self.log.appendPlainText(str(error))

    def on_progress(self, stage, message):
        self.status_label.setText(message)
        self.log.appendPlainText(f'[{stage}] {message}')

    def on_busy(self, busy):
        for widget in (self.run_button, self.open_button, self.save_button, self.history_button):
            widget.setEnabled(not busy)
        self.save_button.setEnabled(not busy and self.current_candidate is not None)
        self.cancel_button.setEnabled(busy)
        self.cad.set_busy(busy)
        self.operation.setEnabled(not busy);self.search.setEnabled(not busy);self.advanced.setEnabled(not busy);self.refresh_parameters()

    def on_finished(self, result):
        self.last_result = result
        self.last_dir = Path(result.get('output_dir', self.last_dir))
        self.status_label.setText('计算完成 · 结构与误差复检通过 · 待人工接受' if result.get('operation')=='optimize' and result.get('decision')=='accepted'
            else f"{result['status']} · {result.get('decision')} · {result.get('quality_status')}")
        self.log.appendPlainText('结果保存于 ' + str(self.last_dir))
        self.report_button.setEnabled((self.last_dir / 'report.html').exists() and (not result.get('report_error')))
        if self.report_button.isEnabled():
            self.report_viewer.load_report(self.last_dir / 'report.html')
        if result.get('operation') == 'convert':
            self.status_label.setText(f"CAD：{result['status']} · 几何检查：{result.get('geometry_status', 'not_run')} · 正式网格版本不改变")
            self.conversion_results.display(result)
            self.load_conversion_preview(result)
            self.workspace.setCurrentWidget(self.conversion_results)
            return
        if result.get('operation')=='evaluate':
            self.evaluation_result=result
            try:
                reference=load_asset(self.last_dir/'reference.npz')
                request=json.loads((self.last_dir/'request.json').read_text(encoding='utf-8'))
                candidate=load_asset(request['candidate_path'])
                with np.load(self.last_dir/'evaluation_samples.npz',allow_pickle=False) as arrays:details={k:arrays[k] for k in arrays.files}
                self.viewer.show_comparison(reference,candidate,details)
            except Exception as error:self.log.appendPlainText('评价视图：'+str(error))
            return
        self.optimization_result, self.optimization_dir = (result, self.last_dir)
        attempts = result.get('attempts', [])
        self.table.setRowCount(len(attempts))
        for row, item in enumerate(attempts):
            m = item.get('final_metrics', item.get('metrics', {}))
            label='通过复检，待人工接受' if item['decision']=='accepted' else item['decision']
            values = [item['candidate_id'], item.get('actual_faces', '—'), m.get('d95', '—'), m.get('sampled_max', '—'), label, ';'.join(item['reason_codes']) or '未选择']
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(f'{value:.6g}' if isinstance(value, float) else str(value)))
        self.table.resizeColumnsToContents()
        best = result.get('selected_candidate') or result.get('preview_candidate')
        if best:
            for row, item in enumerate(attempts):
                if item['candidate_id'] == best:
                    self.table.selectRow(row)
                    self.select_candidate(row, 0)
                    break

    def select_candidate(self, row, _column):
        if not self.optimization_result or self.jobs.busy or self.current_asset is None:
            return
        attempts = self.optimization_result.get('attempts', [])
        if row >= len(attempts):
            return
        item = attempts[row]
        if not item.get('mesh_path'):
            return
        if self.optimization_result.get('input_version') != self.current_asset.version_id:
            self.log.appendPlainText('拒绝绑定：任务参考版本已失配')
            return
        candidate = load_asset(item['mesh_path'])
        details_path = Path(item['final_samples_path']) if item.get('final_samples_path') else Path(item['mesh_path']).parent / (item['candidate_id'] + ('_final.npz' if item.get('final_metrics') else '_screening.npz'))
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
        path, _ = QFileDialog.getSaveFileName(self, '保存候选预览包（不提交正式版本）', 'candidate_preview.npz', 'NPZ (*.npz)')
        if path:
            save_asset(self.current_candidate, path)
            self.log.appendPlainText('已保存候选预览；参考版本未改变。')

    def open_report(self):
        if self.last_dir:
            self.report_viewer.load_report(self.last_dir / 'report.html')
            self.workspace.setCurrentWidget(self.report_viewer)

    def load_conversion_preview(self, result):
        self.viewer.clear_models()
        assets = result.get('preview_assets')
        if not assets:
            return
        try:
            reference, candidate = (load_asset(assets['reference']), load_asset(assets['candidate']))
            with np.load(assets['distances'], allow_pickle=False) as arrays:
                details = {k: arrays[k] for k in arrays.files}
            self.viewer.show_comparison(reference, candidate, details)
            self.viewer.context.setText(f"{(result.get('source_format') or '?').upper()} → {(result.get('target_format') or '?').upper()}\u3000｜\u3000左：输入参考\u3000右：独立回读\u3000｜\u3000距离与坐标：mm")
        except Exception as error:
            self.log.appendPlainText('无法显示转换预览：' + str(error))

    def open_saved_task(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开已保存任务或报告', str(self.root / 'runs'), '任务报告 (result.json report.html *.html)')
        if path:
            try:
                self.load_saved_task(path)
            except Exception as error:
                self.status_label.setText('打开失败：' + str(error))

    def load_saved_task(self, path):
        if self.jobs.busy:
            raise RuntimeError('任务运行中，请等待结束')
        path = Path(path).resolve()
        directory = path.parent
        if not (directory / 'report.html').is_file() or path.suffix not in ('.json', '.html'):
            raise ValueError('请选择任务目录中的result.json或HTML报告')
        result_path = directory / 'result.json'
        self.viewer.clear_models()
        if path.name == 'report.html' and result_path.is_file() or path.name == 'result.json':
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if not isinstance(result, dict):
                raise ValueError('任务记录格式不正确')
            result['output_dir'] = str(directory)
            self.on_finished(result)
        else:
            self.last_dir = directory
            self.last_result = None
            self.conversion_results.reset()
            self.conversion_results.summary.setText('此文件为汇总报告，请在任务报告页阅读。')
        self.report_viewer.load_report(path if path.suffix == '.html' else directory / 'report.html')
        self.workspace.setCurrentWidget(self.report_viewer)
        self.report_button.setEnabled(True)

    def closeEvent(self, event):
        if self.jobs.busy:
            self.jobs.cancel()
            self.log.appendPlainText('正在取消任务，结束后可关闭窗口。')
            event.ignore()
            return
        self.viewer.close_viewer()
        super().closeEvent(event)
