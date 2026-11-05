"""One-window defense controls and an evidence-oriented experiment overview."""
from pathlib import Path
import json
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSpinBox,
    QProgressBar,QTableWidget,QTableWidgetItem,QHeaderView,QComboBox,QCheckBox,QLineEdit,QFileDialog,QScrollArea)
from medical_mesh.experiments.demo import PHASES,DIRECTIONS
from medical_mesh.core.model import write_json

STATUS={'pending':'未执行','running':'执行中','completed':'完成','failed':'失败','cancelled':'已取消','timeout':'超时',
        'passed':'通过','not_run':'未执行','written':'已写出','loaded':'已回读'}


class PatellaDemoPanel(QWidget):
    run_requested=Signal()
    replay_requested=Signal(str)
    comparison_requested=Signal()
    report_requested=Signal()

    def __init__(self,root):
        super().__init__();self.root=Path(root)
        outer=QVBoxLayout(self)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True)
        content=QWidget();layout=QVBoxLayout(content);self.scroll.setWidget(content);outer.addWidget(self.scroll)
        title=QLabel('真实MRI髌骨 · 课设演示');title.setStyleSheet('font-size:18px;font-weight:600;color:#204c60');title.setWordWrap(True)
        layout.addWidget(title)
        intro=QLabel('SPL Knee Atlas公开MRI重建模型\n原始49,862面，长度单位mm。\n来源与许可证、原始文件哈希随任务保存。')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.run_button=QPushButton('一键重新运行完整实验');self.run_button.setMinimumHeight(44)
        self.run_button.clicked.connect(self.run_requested);layout.addWidget(self.run_button)
        hint=QLabel('重新计算通常需数分钟；首次下载77MiB。\n每次新建任务目录。')
        hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();row.addWidget(QLabel('整项超时'))
        self.timeout=QSpinBox();self.timeout.setRange(1,60);self.timeout.setValue(15);self.timeout.setSuffix(' 分钟');row.addWidget(self.timeout)
        layout.addLayout(row)
        self.output_root=QLineEdit(str(self.root/'runs'))
        self.output_button=QPushButton('保存位置…');row=QHBoxLayout();row.addWidget(self.output_root,1);row.addWidget(self.output_button);layout.addLayout(row)
        self.output_button.clicked.connect(self.choose_output)
        self.keep_samples=QCheckBox('保留所有中间采样（至少512MiB空余）');layout.addWidget(self.keep_samples)
        storage=QLabel('默认保留优化候选与六次回读的完整采样，\n其余保存指标和种子；计算点数不变。');storage.setWordWrap(True);layout.addWidget(storage)
        layout.addWidget(QLabel('历史结果查看（不重新计算）'))
        self.history=QComboBox();self.history.setMinimumContentsLength(15);layout.addWidget(self.history)
        self.replay_button=QPushButton('载入所选历史实验')
        self.replay_button.clicked.connect(lambda:self.replay_requested.emit(self.history.currentData() or ''))
        layout.addWidget(self.replay_button)
        self.compare_button=QPushButton('原始 / 优化模型对比');self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self.comparison_requested);layout.addWidget(self.compare_button)
        self.report_button=QPushButton('查看本次实验总报告');self.report_button.setEnabled(False)
        self.report_button.clicked.connect(self.report_requested);layout.addWidget(self.report_button)
        self.directory=QLabel('尚未选择演示任务');self.directory.setWordWrap(True);self.directory.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.directory)
        scope=QLabel('每方向50,000点，保持原阈值和种子。\n工作模型不被覆盖；候选仍需完整诊断。')
        scope.setWordWrap(True);layout.addWidget(scope);layout.addStretch()
        self.refresh_history()

    def refresh_history(self):
        chosen=self.history.currentData();self.history.clear()
        runs=self.root/'runs'
        files=list(runs.glob('*/demo_result.json')) if runs.exists() else []
        paths=[p.parent for p in sorted(files,key=lambda p:p.stat().st_mtime,reverse=True)[:20]]
        registry=runs/'patella_demo_history.json'
        if registry.exists():
            try:
                registered=json.loads(registry.read_text())
                paths=[Path(p) for p in registered if isinstance(p,str) and (Path(p)/'demo_result.json').exists()]+paths
            except (OSError,ValueError,TypeError):pass
        paths=list(dict.fromkeys(paths))[:20]
        baseline=runs/'medical_patella_verified_20261022'
        if (baseline/'artifact_verification.json').exists():paths.append(baseline)
        for path in paths:
            self.history.addItem(path.name,str(path))
        if chosen:
            index=self.history.findData(chosen)
            if index>=0:self.history.setCurrentIndex(index)
        self.replay_button.setEnabled(self.history.count()>0)

    def remember(self,directory):
        paths=[str(directory)]+[self.history.itemData(i) for i in range(self.history.count())]
        write_json(self.root/'runs/patella_demo_history.json',list(dict.fromkeys(paths))[:20])

    def choose_output(self):
        path=QFileDialog.getExistingDirectory(self,'选择实验保存目录',self.output_root.text())
        if path:self.output_root.setText(path)

    def set_busy(self,busy):
        for widget in (self.run_button,self.history,self.timeout,self.output_root,self.output_button,self.keep_samples):widget.setEnabled(not busy)
        self.replay_button.setEnabled(not busy and self.history.count()>0)
        # Inspection of current results remains available during calculations.


class PatellaDemoOverview(QWidget):
    conversion_requested=Signal(str)
    conversion_report_requested=Signal(str)

    def __init__(self):
        super().__init__();layout=QVBoxLayout(self)
        self.mode=QLabel('尚未开始真实模型演示');self.mode.setStyleSheet('font-size:18px;color:#20566b');self.mode.setWordWrap(True);layout.addWidget(self.mode)
        self.detail=QLabel('点击左侧“一键重新运行完整实验”，或载入已验证的历史结果。');self.detail.setWordWrap(True);layout.addWidget(self.detail)
        self.bar=QProgressBar();self.bar.setRange(0,len(PHASES));self.bar.setValue(0);self.bar.setFormat('已完成阶段 %v / %m');layout.addWidget(self.bar)
        self.phases=QTableWidget(1,len(PHASES));self.phases.setHorizontalHeaderLabels(['来源与模型','优化及种子复核','六向转换回读','负对照','报告与审计'])
        self.phases.setFixedHeight(60);self.phases.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.phases)
        self.optimization=QTableWidget(0,6);self.optimization.setHorizontalHeaderLabels(['优化方案','实际面数','D95/mm','采样最大/mm','单次几何','追加种子'])
        self.optimization.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.optimization.setMinimumHeight(140)
        layout.addWidget(self.optimization,1)
        self.selected=QLabel('尚无最终研究候选');self.selected.setWordWrap(True);layout.addWidget(self.selected)
        self.conversions=QTableWidget(6,7)
        self.conversions.setHorizontalHeaderLabels(['方向','文件写出','独立回读','几何检查','转换D95/mm','端到端D95/mm','当前步骤'])
        self.conversions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.conversions.setFixedHeight(188);layout.addWidget(self.conversions)
        row=QHBoxLayout();self.view_conversion=QPushButton('查看选中方向的回读模型 / 指标');self.view_report=QPushButton('查看选中方向的详细报告')
        row.addWidget(self.view_conversion);row.addWidget(self.view_report);layout.addLayout(row)
        scope=QLabel('转换D95只衡量格式步骤；端到端D95相对原始MRI模型。微小数值不代表同等解剖精度。')
        scope.setWordWrap(True);layout.addWidget(scope)
        self.view_conversion.clicked.connect(lambda:self.emit_direction(False));self.view_report.clicked.connect(lambda:self.emit_direction(True))
        for table in (self.phases,self.optimization,self.conversions):
            table.setEditTriggers(QTableWidget.NoEditTriggers);table.setSelectionBehavior(QTableWidget.SelectRows)
            table.verticalHeader().hide();table.verticalHeader().setMinimumSectionSize(20);table.verticalHeader().setDefaultSectionSize(24)
        self.conversions.cellDoubleClicked.connect(lambda r,c:self.emit_direction(False))
        self.rows={};self.available=set();self.reset()

    def emit_direction(self,report):
        row=self.conversions.currentRow()
        if row>=0 and DIRECTIONS[row] in self.available:
            (self.conversion_report_requested if report else self.conversion_requested).emit(DIRECTIONS[row])

    def reset(self,replay=False):
        self.rows={};self.available=set();self.optimization.setRowCount(0);self.bar.setValue(0)
        self.mode.setText('历史记录查看 · 未重新计算' if replay else '实际重新计算 · 正式参考版本保持不变')
        self.detail.setText('等待任务阶段消息');self.selected.setText('尚无本次最终研究候选')
        for r,(key,title) in enumerate(PHASES):
            self.phases.setItem(0,r,QTableWidgetItem('未执行'))
        for r,direction in enumerate(DIRECTIONS):
            for c in range(7):self.conversions.setItem(r,c,QTableWidgetItem(direction.replace('_to_',' → ').upper() if c==0 else '未执行'))
        self.view_conversion.setEnabled(False);self.view_report.setEnabled(False)

    def phases_update(self,phases):
        count=0
        for r,(key,title) in enumerate(PHASES):
            status=phases.get(key,{}).get('status','pending');count+=status=='completed'
            self.phases.setItem(0,r,QTableWidgetItem(STATUS.get(status,status)))
        self.bar.setValue(count)

    def candidate_update(self,row):
        name=row['label'];self.rows[name]=row;self.optimization.setRowCount(len(self.rows))
        for r,item in enumerate(self.rows.values()):
            metrics=item.get('final_metrics',{})
            seed='通过' if item.get('stability_passed') else '未通过' if 'stability_passed' in item else '未执行'
            values=[item['label'],item.get('actual_faces','—'),metrics.get('d95'),metrics.get('sampled_max'),
                    '通过' if item.get('geometry_final_pass') else '未通过',seed]
            for c,value in enumerate(values):
                self.optimization.setItem(r,c,QTableWidgetItem('—' if value is None else f'{value:.6g}' if isinstance(value,float) else str(value)))

    def conversion_update(self,direction,result=None,stage=None):
        r=DIRECTIONS.index(direction)
        if result is not None:
            metric=result.get('metrics',{});end=result.get('end_to_end_original',{})
            values=[result.get('export_status','not_run'),result.get('readback_status','not_run'),result.get('geometry_status','not_run'),
                    metric.get('d95',result.get('d95_mm')),end.get('d95',result.get('end_to_end_d95_mm')),result.get('status','未执行')]
            for c,value in enumerate(values,1):
                self.conversions.setItem(r,c,QTableWidgetItem('—' if value is None else f'{value:.6g}' if isinstance(value,float) else STATUS.get(value,str(value))))
            self.available.add(direction);self.view_conversion.setEnabled(True);self.view_report.setEnabled(True)
            if self.conversions.currentRow()<0:self.conversions.selectRow(r)
        elif stage:
            labels={'exporting':'正在写出','readback_fine':'细档独立回读','readback_coarse':'粗档独立回读',
                    'source_reference':'读取源CAD参考','evaluating':'双向距离检查','end_to_end_original':'相对原始医学模型评价','chain_vs_selected':'量化与完整来源链评价'}
            self.conversions.setItem(r,6,QTableWidgetItem(labels.get(stage,stage)))
            if stage in ('readback_fine','readback_coarse','source_reference','evaluating'):
                self.conversions.setItem(r,1,QTableWidgetItem('已写出'))
            if stage in ('end_to_end_original','chain_vs_selected'):
                self.conversions.setItem(r,2,QTableWidgetItem('已回读'))
