"""Embeddable member 1 page. Host owns the window and may supply its viewer."""
import json
import sys
import uuid
import time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QProcess,QProcessEnvironment,QTimer,Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QFileDialog,
                              QLabel,QCheckBox,QListWidget,QListWidgetItem,QDoubleSpinBox,
                              QComboBox,QSplitter,QPlainTextEdit,QAbstractItemView,QSlider,QScrollArea,QProgressBar,QSpinBox,QTableWidget,QTableWidgetItem)
from PySide6.QtCore import Qt
from ..io.mesh_io import load_mesh,save_mesh
from ..core.versions import VersionStore
from .selection import diagnostic_items
from .picking import nearest_boundary
from ..core.review import CandidateReview,comparison_rows
from ..core.boundary_roles import BoundaryRoles,ROLES
from ..core.project_bundle import export_summary,save_project


class Member1Panel(QWidget):
    asset_changed=Signal(object)
    diagnosis_changed=Signal(dict)
    preview_changed=Signal(dict)
    task_finished=Signal(dict)
    export_finished=Signal(dict)
    review_resolved=Signal(dict)

    def __init__(self,viewer,session_root,parent=None):
        super().__init__(parent)
        self.viewer=viewer
        self.root=Path(session_root)
        self.store=VersionStore(self.root/"versions")
        self.boundary_roles=BoundaryRoles(self.root/'boundary_roles.json')
        self.suggestions=[]
        self.suggestions_version=None
        self.asset=None
        self.diagnosis=None
        self.process=None
        self.cancelled=False
        self.timed_out=False
        self.job_root=None
        self.pending_review=None
        self.redo_stack=[]
        self.accepted_diagnosis=None
        layout=QVBoxLayout(self)
        title=QLabel("医学三维模型 · 导入、诊断与受控修复")
        title.setStyleSheet("font-size:20px;font-weight:600;padding:8px")
        layout.addWidget(title)
        toolbar=QHBoxLayout()
        self.import_button=QPushButton("导入模型")
        self.diagnose_button=QPushButton("重新检测")
        self.undo_button=QPushButton("回退上一版本")
        self.export_button=QPushButton("导出已接受版本")
        self.cancel_button=QPushButton("取消任务")
        for button in (self.import_button,self.diagnose_button,self.undo_button,self.export_button,self.cancel_button):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        units=QHBoxLayout()
        units.addWidget(QLabel("导入单位（不改变坐标）："))
        self.units=QComboBox();self.units.addItems(["未知","mm","cm","m"])
        units.addWidget(self.units)
        self.wire=QCheckBox("线框");units.addWidget(self.wire)
        self.self_check=QCheckBox("检测自交（PyMeshLab）");units.addWidget(self.self_check)
        self.simplify=QCheckBox('大模型简化显示（仅视图）');self.simplify.setChecked(True);units.addWidget(self.simplify)
        units.addStretch();layout.addLayout(units)
        navigation=QHBoxLayout()
        self.view_preset=QComboBox();self.view_preset.addItems(['等轴测','正面 XY','侧面 YZ','顶部 XZ'])
        navigation.addWidget(QLabel('观察方向'));navigation.addWidget(self.view_preset)
        navigation.addWidget(QLabel('模型不透明度'))
        self.opacity=QSlider(Qt.Horizontal);self.opacity.setRange(15,100);self.opacity.setValue(100);self.opacity.setMaximumWidth(180)
        navigation.addWidget(self.opacity)
        self.pick_boundary=QCheckBox('在视图中选孔（右键点击孔边）')
        navigation.addWidget(self.pick_boundary)
        self.snapshot_button=QPushButton('保存当前视图')
        navigation.addWidget(self.snapshot_button);navigation.addStretch();layout.addLayout(navigation)
        self.summary=QLabel("请导入 STL、PLY、OBJ 或 NPZ；天然开口默认保留。")
        self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.export_info=QLabel('导出尺寸与单位将在导入后显示。');self.export_info.setWordWrap(True)
        layout.addWidget(self.export_info)
        self.display_info=QLabel('');layout.addWidget(self.display_info)
        splitter=QSplitter()
        controls=QWidget();control=QVBoxLayout(controls)
        control.addWidget(QLabel("诊断对象（点击定位；边界需先标记用途）"))
        self.defects=QListWidget();self.defects.setSelectionMode(QAbstractItemView.ExtendedSelection)
        control.addWidget(self.defects)
        self.selection_help=QLabel('点击诊断项查看颜色含义；黄色为边，紫色为退化线段 / 异常顶点。')
        self.selection_help.setWordWrap(True)
        self.selection_help.setStyleSheet('padding:8px;background:#eaf3f5;color:#15333c;')
        control.addWidget(self.selection_help)
        view_buttons=QHBoxLayout()
        self.focus_button=QPushButton('定位并放大选中对象')
        self.overview_button=QPushButton('恢复全貌')
        view_buttons.addWidget(self.focus_button);view_buttons.addWidget(self.overview_button)
        control.addLayout(view_buttons)
        self.auto_focus=QCheckBox('点击问题时自动定位局部');self.auto_focus.setChecked(True)
        control.addWidget(self.auto_focus)
        self.conflict_edge_choice=QComboBox();self.conflict_edge_choice.setToolTip('逐条查看方向冲突边，避免多组箭头重叠');self.conflict_edge_choice.currentIndexChanged.connect(lambda _:self.highlight());control.addWidget(self.conflict_edge_choice)
        roles_row=QHBoxLayout()
        self.boundary_role=QComboBox()
        for key,label in ROLES.items():self.boundary_role.addItem(label,key)
        self.mark_role_button=QPushButton('标记选中边界')
        roles_row.addWidget(self.boundary_role);roles_row.addWidget(self.mark_role_button)
        control.addLayout(roles_row)
        self.boundary_table=QTableWidget(0,2);self.boundary_table.setHorizontalHeaderLabels(['边界（逐孔独立设置）','用途']);self.boundary_table.setMaximumHeight(190);self.boundary_table.setMinimumHeight(100);self.boundary_table.horizontalHeader().setStretchLastSection(True);control.addWidget(self.boundary_table)
        self.boundary_advice_button=QPushButton('智能识别补洞建议（需确认）');control.addWidget(self.boundary_advice_button);self.boundary_advice_button.clicked.connect(self.suggest_boundary_roles)
        self.confirm_advice_button=QPushButton('确认采用小孔建议（保留已标记用途）');self.confirm_advice_button.clicked.connect(self.confirm_boundary_advice);control.addWidget(self.confirm_advice_button)
        self.boundary_advice_text=QLabel('智能建议仅依据几何；天然开口不能仅凭大小自动判定。');self.boundary_advice_text.setWordWrap(True);control.addWidget(self.boundary_advice_text)
        self.target_summary=QLabel('补洞目标：无；未标记边界默认保留。')
        self.target_summary.setWordWrap(True);control.addWidget(self.target_summary)
        self.clean_duplicates=QCheckBox("删除重复面")
        self.clean_degenerate=QCheckBox("删除退化面")
        self.orient=QCheckBox("法线方向一致化")
        for check in (self.clean_duplicates,self.clean_degenerate,self.orient): control.addWidget(check)
        control.addWidget(QLabel("补洞最大跨度（原坐标单位）；最多64条边"))
        self.hole_span=QDoubleSpinBox();self.hole_span.setRange(.001,100000);self.hole_span.setValue(10)
        control.addWidget(self.hole_span)
        self.hole_method=QComboBox()
        self.hole_method.addItem('近共面孔：平面三角化（默认）','planar')
        self.hole_method.addItem('局部二次曲面拟合（实验，仅凸孔）','quadric')
        self.hole_method.addItem('邻域曲面补片（实验，支持凹孔与内部加点）','surface')
        self.hole_method.setToolTip('邻域曲面模式支持6—64边的简单高度场孔，固定边界并在内部加点；强制自交复检，需查看修复预览。')
        control.addWidget(self.hole_method)
        self.repair_button=QPushButton("生成修复预览")
        control.addWidget(self.repair_button)
        self.review_summary=QLabel('先选择策略并生成预览；检查结果后再接受。')
        self.review_summary.setWordWrap(True);self.review_summary.setTextFormat(Qt.RichText)
        control.addWidget(self.review_summary)
        self.preview_side=QComboBox();self.preview_side.addItems(['观察修复后预览','观察修复前输入'])
        self.preview_side.setEnabled(False)
        review_buttons=QHBoxLayout()
        self.accept_button=QPushButton('接受预览结果');self.discard_button=QPushButton('放弃预览')
        review_buttons.addWidget(self.accept_button);review_buttons.addWidget(self.discard_button)
        control.addWidget(QLabel("非流形处理建议（先复检，再由你选择）"))
        self.suggest_button=QPushButton('查找删面组合 / 顶点拆分建议')
        control.addWidget(self.suggest_button)
        budget_row=QHBoxLayout();budget_row.addWidget(QLabel('候选复检预算（受限搜索）'))
        self.suggestion_budget=QSpinBox();self.suggestion_budget.setRange(1,48);self.suggestion_budget.setValue(12)
        budget_row.addWidget(self.suggestion_budget);control.addLayout(budget_row)
        self.suggestion_choice=QComboBox();self.suggestion_choice.addItem('尚未生成建议')
        control.addWidget(self.suggestion_choice)
        self.suggestion_status=QLabel('先查找建议，再选择方案查看位置与结构变化，最后生成修复预览。');self.suggestion_status.setWordWrap(True);control.addWidget(self.suggestion_status)
        self.apply_suggestion_button=QPushButton('查看方案并填入删除面编号')
        control.addWidget(self.apply_suggestion_button)
        control.addWidget(QLabel("删除原面索引（逗号分隔；生成预览后才可接受）"))
        from PySide6.QtWidgets import QLineEdit
        self.delete_ids=QLineEdit();self.delete_ids.setPlaceholderText("例如 12,18；留空则保留")
        control.addWidget(self.delete_ids)
        self.split_ids=QLineEdit();self.split_ids.setPlaceholderText('拆分顶点编号（逗号分隔，默认不拆分）')
        control.addWidget(self.split_ids)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(controls)
        self.controls_scroll=scroll
        scroll.setMinimumWidth(350);scroll.setMaximumWidth(530)
        splitter.addWidget(scroll);splitter.addWidget(viewer.interactor)
        splitter.setSizes([360,800]);layout.addWidget(splitter,1)
        self.review_banner=QLabel('修复流程：生成预览 → 检查前后指标 → 接受或放弃')
        compare_tools=QHBoxLayout()
        self.dual_view=QCheckBox('同步双视图对照');self.dual_view.setChecked(True)
        self.dual_view.setToolTip('左侧为下拉框选择的当前版本，右侧为另一版本；两边共享相机。AFTER为修复后，BEFORE为修复前。')
        self.show_changes=QCheckBox('显示修复变化');self.show_changes.setChecked(True)
        self.focus_changes_button=QPushButton('定位改动')
        compare_tools.addWidget(self.dual_view);compare_tools.addWidget(self.show_changes)
        compare_tools.addWidget(self.focus_changes_button)
        self.change_legend=QLabel('绿色：新增面　红色：删除面（修复前）　橙色：翻转面')
        self.change_legend.setWordWrap(True);compare_tools.addWidget(self.change_legend,1)
        layout.addLayout(compare_tools)
        self.patch_summary=QLabel('补片质量将在补洞预览中显示。')
        self.patch_summary.setWordWrap(True);layout.addWidget(self.patch_summary)
        self.patch_summary.setMinimumHeight(self.fontMetrics().lineSpacing()*3+8)
        review_buttons.insertWidget(0,self.review_banner,1)
        review_buttons.insertWidget(1,self.preview_side)
        layout.addLayout(review_buttons)
        task_row=QHBoxLayout();self.task_stage=QLabel('后台任务：空闲')
        self.task_progress=QProgressBar();self.task_progress.setMaximumWidth(160);self.task_progress.setRange(0,0);self.task_progress.hide()
        task_row.addWidget(self.task_stage,1);task_row.addWidget(self.task_progress);layout.addLayout(task_row)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(140);layout.addWidget(self.log)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self._timeout)
        self.progress_timer=QTimer(self);self.progress_timer.setInterval(250);self.progress_timer.timeout.connect(self.update_progress)
        self.import_button.clicked.connect(self.import_mesh)
        self.diagnose_button.clicked.connect(lambda:self.start_job("diagnose"))
        self.repair_button.clicked.connect(self.repair)
        self.undo_button.clicked.connect(self.rollback)
        self.export_button.clicked.connect(self.export)
        self.cancel_button.clicked.connect(self.cancel)
        self.defects.itemSelectionChanged.connect(self.selection_changed)
        self.mark_role_button.clicked.connect(self.mark_boundary_role)
        self.suggest_button.clicked.connect(self.request_suggestions)
        self.apply_suggestion_button.clicked.connect(self.apply_suggestion)
        self.focus_button.clicked.connect(lambda:self.focus_selected(manual=True))
        self.overview_button.clicked.connect(self.show_overview)
        self.wire.toggled.connect(lambda _:self.render())
        self.simplify.toggled.connect(self.change_display_mode)
        self.view_preset.currentIndexChanged.connect(self.change_view)
        self.opacity.valueChanged.connect(self.change_opacity)
        self.pick_boundary.toggled.connect(self.enable_boundary_picking)
        self.snapshot_button.clicked.connect(self.save_snapshot)
        self.accept_button.clicked.connect(self.accept_preview)
        self.discard_button.clicked.connect(self.discard_preview)
        self.preview_side.currentIndexChanged.connect(self.switch_preview_side)
        self.dual_view.toggled.connect(lambda _:self.render())
        self.show_changes.toggled.connect(lambda _:self.render())
        self.focus_changes_button.clicked.connect(self.focus_changes)
        self.store.subscribe(lambda _:self.viewer.clear_highlights())
        self._busy(False)

    def _busy(self,busy):
        for button in (self.import_button,self.diagnose_button,self.repair_button,self.undo_button,self.export_button):
            button.setEnabled(not busy and self.pending_review is None and (button is self.import_button or self.asset is not None))
        self.accept_button.setEnabled(not busy and self.pending_review is not None)
        self.discard_button.setEnabled(not busy and self.pending_review is not None)
        self.preview_side.setEnabled(not busy and self.pending_review is not None)
        for widget in (self.dual_view,self.show_changes,self.focus_changes_button):widget.setEnabled(not busy and self.pending_review is not None)
        self.change_legend.setVisible(self.pending_review is not None)
        self.review_banner.setText('待接受预览：原版本未替换；可切换修复前后观察。' if self.pending_review else '修复流程：生成预览 → 检查前后指标 → 接受或放弃')
        self.units.setEnabled(not busy)
        self.task_progress.setVisible(busy)
        for button in (self.mark_role_button,self.suggest_button,self.apply_suggestion_button):
            button.setEnabled(not busy and self.asset is not None and self.pending_review is None)
        self.cancel_button.setEnabled(busy)

    def import_mesh(self):
        path,_=QFileDialog.getOpenFileName(self,"导入模型或项目包","","网格与项目 (*.stl *.obj *.ply *.npz *.m3d)")
        if path: self.start_job("load",input_path=path)

    def start_job(self,operation,input_path=None,parameters=None):
        if self.process is not None:return
        if self.pending_review is not None:
            self.log.appendPlainText('请先接受或放弃当前预览。');return
        if input_path is None and self.asset is None:return
        self.active_operation=operation
        if operation=='load':self.requested_source=str(input_path)
        self.job_root=self.root/"jobs"/uuid.uuid4().hex
        self.job_root.mkdir(parents=True)
        if input_path is None:
            input_path=str(self.job_root/"input.npz");save_mesh(self.asset,input_path)
        request={"operation":operation,"run_id":self.job_root.name,"input_path":input_path,
                 "output_dir":str(self.job_root.resolve()),"parameters":parameters or {"check_self_intersection":self.self_check.isChecked()}}
        if operation=="load" and self.units.currentText()!="未知":
            unit=self.units.currentText()
            request["read_options"]={"source_unit":unit,"unit_to_mm":{"mm":1,"cm":10,"m":1000}[unit]}
        request_path=self.job_root/"request.json"
        request_path.write_text(json.dumps(request,ensure_ascii=False),encoding="utf-8")
        self.cancelled=False;self.timed_out=False
        self.process=QProcess(self)
        environment=QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONPATH",str(Path(__file__).resolve().parents[2]))
        self.process.setProcessEnvironment(environment)
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-m","medical_mesh.processing.mesh_worker",str(request_path.resolve())])
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self._busy(True);self.log.appendPlainText("运行："+operation)
        large=(self.asset is not None and len(self.asset.faces)>=50000) or (Path(input_path).exists() and Path(input_path).stat().st_size>=10_000_000)
        self.timer.start(600000 if large else 120000)
        self.task_stage.setText('后台任务：准备启动');self.progress_timer.start();self.process.start()
        self.job_started=time.monotonic()

    def update_progress(self):
        if self.job_root is None:return
        path=self.job_root/'progress.json'
        if path.exists():
            try:
                state=json.loads(path.read_text(encoding='utf-8'))
                self.task_stage.setText(f"后台阶段：{state['stage']} ｜ 已运行 {time.monotonic()-self.job_started:.1f}秒")
            except (OSError,ValueError,KeyError):pass

    def process_error(self,error):
        if self.process and error==QProcess.FailedToStart:
            self.log.appendPlainText("工作进程启动失败："+self.process.errorString())
            self.timer.stop();self.process.deleteLater();self.process=None;self._busy(False)
            self.progress_timer.stop();self.task_stage.setText('后台任务启动失败')

    def _timeout(self):
        self.timed_out=True
        if self.process:self.process.kill()

    def cancel(self):
        if self.process:
            self.cancelled=True;self.process.kill()

    def finished(self,*_):
        self.timer.stop()
        data={}
        try:
            if self.cancelled or self.timed_out:
                status="cancelled" if self.cancelled else "failed"
                data={"status":status,"errors":["用户取消" if self.cancelled else "后台任务达到时限"],
                      "input_version":self.asset.version if self.asset else "unknown","output_version":None,
                      "metrics":{},"warnings":[],"elapsed_seconds":0,"output_paths":{},"quality_status":"unverified"}
                (self.job_root/"result.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                (self.job_root/'progress.json').write_text(json.dumps(dict(stage=data['errors'][0],status=status,
                    elapsed_seconds=time.monotonic()-self.job_started),ensure_ascii=False),encoding='utf-8')
                self.log.appendPlainText(data["errors"][0]);return
            data=json.loads((self.job_root/"result.json").read_text(encoding="utf-8"))
            self.log.appendPlainText(data["status"]+": "+"; ".join(data["errors"]+data["warnings"]))
            if data["status"]=="completed":
                if 'suggestions' in data.get('metrics',{}):
                    if data['input_version']!=self.asset.version:
                        self.log.appendPlainText('建议来自旧版本，已忽略。');return
                    self.suggestions=data['metrics']['suggestions']
                    self.suggestions_version=self.asset.version
                    self.suggestion_choice.clear();self.suggestion_choice.addItem('请选择方案（不会自动修改模型）')
                    for proposal in self.suggestions:
                        label=(f"拆分顶点 {proposal.get('split_vertex_ids',[])}" if proposal.get('split_vertex_ids') else f"删除面 {proposal['delete_face_ids']}")
                        self.suggestion_choice.addItem(label+f" · 闭环{proposal['boundary_loops_before']}→{proposal['boundary_loops_after']} · 分量{proposal['components_before']}→{proposal['components_after']}")
                    message=f"搜索结束：检查 {data['metrics']['examined']} 个候选，找到 {len(self.suggestions)} 个通过方案。"
                    message+=' 请在下方选择方案，再点击“查看方案”。' if self.suggestions else ' 本轮未找到通过方案，可提高预算后重试；不代表不存在可行修复。'
                    self.suggestion_status.setText(message);self.suggestion_status.setStyleSheet('padding:8px;background:#fff0cf;color:#725218;')
                    self.controls_scroll.ensureWidgetVisible(self.suggestion_choice)
                    if self.suggestions:self.suggestion_choice.showPopup()
                    self.log.appendPlainText(f"已验证 {data['metrics']['examined']} 个候选，{len(self.suggestions)} 个方案通过复检。")
                    if data['metrics']['truncated']:self.log.appendPlainText('候选预算已用尽；这是受限搜索，并非完整搜索。')
                    return
                candidate=load_mesh(data["output_paths"]["mesh"])
                if getattr(self,'active_operation',None)=='load':self.loaded_source=self.requested_source
                if 'diagnosis_after' in data:
                    self.pending_review=CandidateReview(self.asset,candidate,data,self.job_root)
                    changes=data['metrics']['changes']
                    quality=data['metrics']['patch_quality']
                    self.patch_summary.setText(self.quality_text(quality)+
                        f"\n变化：新增 {len(changes['added_face_ids'])} 面，删除 {len(changes['removed_face_ids'])} 面，翻转 {len(changes['flipped_output_face_ids'])} 面。")
                    self.preview_side.blockSignals(True);self.preview_side.setCurrentIndex(0);self.preview_side.blockSignals(False)
                    rows=comparison_rows(data['diagnosis_before'],data['diagnosis_after'])
                    table='<table width="100%"><tr><th>指标</th><th>当前</th><th>预览</th></tr>'
                    table+=''.join(f'<tr><td>{name}</td><td align="center">{a}</td><td align="center">{b}</td></tr>' for name,a,b in rows)
                    kind='优化' if any(op.get('operation')=='member2_optimization' for op in data.get('operations',[])) else '修复'
                    self.review_summary.setText('<b>待接受的'+kind+'预览</b>'+table+'</table>原版本尚未替换；自交状态：'+data['diagnosis_after']['self_intersection']['status'])
                    self.bind_diagnosis(data['diagnosis_after']);self.render()
                    if self.auto_focus.isChecked():self.focus_changes()
                    self.log.appendPlainText('修复复检完成。预览尚未提交，请检查后接受或放弃。')
                else:
                    history=self.job_root/'imported_history'
                    if history.exists():
                        for source in history.iterdir():
                            destination=self.store.root/source.name
                            if destination.exists():
                                if source.suffix=='.npz':
                                    old,new=load_mesh(destination),load_mesh(source)
                                    if old.geometry_hash()!=new.geometry_hash() or old.metadata()!=new.metadata():raise ValueError('项目包历史版本冲突')
                            else:destination.write_bytes(source.read_bytes())
                    archived_result=self.store.root/(candidate.version+'.result.json')
                    if self.asset is None or self.asset.version!=candidate.version:self.redo_stack.clear()
                    self.store.commit(candidate,None if archived_result.exists() else data);self.asset=candidate
                    imported=data['metrics'].get('imported_boundary_roles',{})
                    for boundary in data['boundaries']:
                        if str(boundary['id']) in imported:self.boundary_roles.mark(self.asset,[boundary],imported[str(boundary['id'])])
                    self.accepted_diagnosis=data
                    self.review_summary.setText('选择策略并生成预览；检查结果后再接受。')
                    self.patch_summary.setText('补片质量将在补洞预览中显示。')
                    self.asset_changed.emit(self.asset)
                    self.bind_diagnosis(data);self.render()
        except Exception as e:
            self.log.appendPlainText("结果读取失败，保留当前版本："+str(e))
            data={"status":"failed","errors":[str(e)],"input_version":self.asset.version if self.asset else "unknown",
                  "output_version":None,"metrics":{},"warnings":[],"elapsed_seconds":0,
                  "output_paths":{},"quality_status":"unverified"}
            (self.job_root/"result.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        finally:
            self.progress_timer.stop()
            self.task_stage.setText('后台任务：已取消' if self.cancelled else ('后台任务：超时，保留原版本' if self.timed_out else '后台任务：已结束'))
            if self.process:self.process.deleteLater()
            self.process=None;self._busy(False)
            self.task_finished.emit(data)

    def bind_diagnosis(self,data):
        self.diagnosis=data
        # Clear/repopulate atomically: old selection IDs belong to the old asset.
        self.defects.blockSignals(True)
        self.defects.clear()
        m=data["metrics"]
        displayed=self.display_asset()
        unit=displayed.source_unit or "未知（原坐标）"
        info=export_summary(displayed)
        self.export_info.setText(f"原坐标尺寸：{' × '.join(f'{x:.4g}' for x in info['dimensions'])} ｜ 单位：{info['unit']}"
            +(' ｜ 毫米尺寸：'+' × '.join(f'{x:.4g}' for x in info['dimensions_mm']) if info['dimensions_mm'] else ' ｜ 无单位证据，不换算为毫米')
            +(' ｜ 存在重合索引顶点；STL回读可能焊接，建议NPZ/项目包' if info['coincident_indexed_vertices'] else ''))
        prefix=('修复后预览（未提交）' if self.preview_side.currentIndex()==0 else '修复前输入（预览对照）') if self.pending_review else '已接受版本'
        self.summary.setText(f"{prefix} ｜ 顶点 {m['vertex_count']} ｜ 三角面 {m['face_count']} ｜ 连通分量 {m['component_count']} ｜ 边界环 {m['boundary_loop_count']} ｜ 单位 {unit} ｜ 自交 {m['self_intersection_status']}\n版本 {displayed.version}")
        for entry in diagnostic_items(data):
            if 'boundary' in entry:
                role=self.boundary_roles.mapping(displayed,data)[str(entry['boundary'])]
                entry['text']+=' · '+ROLES[role]
            item=QListWidgetItem(entry['text']);item.setToolTip(entry['description'])
            item.setData(256,entry);self.defects.addItem(item)
        self.defects.blockSignals(False)
        roles=self.boundary_roles.mapping(displayed,data)
        self.boundary_table.setRowCount(len(data['boundaries']))
        for row,boundary in enumerate(data['boundaries']):
            self.boundary_table.setItem(row,0,QTableWidgetItem(f"边界 {boundary['id']} · {boundary['edge_count']}边"))
            choice=QComboBox()
            for role,label in ROLES.items():choice.addItem(label,role)
            if boundary['kind']!='simple_loop':choice.model().item(choice.findData('repair_target')).setEnabled(False)
            choice.setCurrentIndex(choice.findData(roles[str(boundary['id'])]));choice.setEnabled(self.pending_review is None and self.process is None)
            choice.currentIndexChanged.connect(lambda _,b=boundary,c=choice:self.set_boundary_role(b,c.currentData()))
            self.boundary_table.setCellWidget(row,1,choice)
        targets=[bid for bid,role in roles.items() if role=='repair_target']
        self.target_summary.setText(('修复后预览：已处理的目标不再列为边界。' if self.pending_review and self.preview_side.currentIndex()==0 else
            '补洞目标：'+(', '.join(targets) if targets else '无'))+' 未标记闭环与天然开口保留。')
        if self.suggestions_version!=displayed.version:
            self.suggestions=[];self.suggestions_version=None
            self.suggestion_choice.clear();self.suggestion_choice.addItem('尚未生成当前版本的建议')
            self.delete_ids.clear()
            self.split_ids.clear()
        self.highlight()
        if self.pending_review:self.preview_changed.emit(data)
        else:self.diagnosis_changed.emit(data)

    def render(self):
        if self.asset:
            self.viewer.set_asset(self.display_asset(),wireframe=self.wire.isChecked())
            self.change_opacity(self.opacity.value())
            self.highlight()
            if hasattr(self.viewer,'set_comparison'):
                self.viewer.set_comparison(self.pending_review,self.preview_side.currentIndex(),
                    self.dual_view.isChecked(),self.show_changes.isChecked(),self.wire.isChecked())
            if self.pick_boundary.isChecked():self.enable_boundary_picking(True)
            self.display_info.setText(getattr(self.viewer,'display_notice',''))

    def change_display_mode(self,enabled):
        if hasattr(self.viewer,'simplify_display'):self.viewer.simplify_display=enabled
        self.render()

    @staticmethod
    def quality_text(quality):
        if quality['status']=='not_applicable':return '本次没有新增补片；不显示补洞质量指标。'
        number=lambda value: '未定义' if value is None else f'{value:.2f}'
        seam='无可测接缝' if quality['maximum_seam_angle_degrees'] is None else f"{quality['maximum_seam_angle_degrees']:.2f}°"
        text=(f"补片 {quality['face_count']} 面 ｜ 最小角 {number(quality['minimum_angle_degrees'])}°"
              f" ｜ 最大长宽比 {number(quality['maximum_aspect_ratio'])}"
              f" ｜ 接缝最大法线夹角 {seam}")
        return text+'\n'+('；'.join(quality['warnings']) if quality['warnings'] else '所列几何提示阈值未触发。')+' 这些指标不代表解剖形状恢复准确度。'

    def focus_changes(self):
        if self.pending_review and hasattr(self.viewer,'focus_review_changes'):
            self.viewer.focus_review_changes(self.pending_review)

    def display_asset(self):
        if self.pending_review:
            return self.pending_review.candidate if self.preview_side.currentIndex()==0 else self.pending_review.input_asset
        return self.asset

    def switch_preview_side(self):
        if self.pending_review:
            key='diagnosis_after' if self.preview_side.currentIndex()==0 else 'diagnosis_before'
            self.bind_diagnosis(self.pending_review.result[key]);self.render()

    def highlight(self):
        if self.asset is None:return
        selected=[x.data(256) for x in self.defects.selectedItems()]
        orientation=next((x for x in selected if x['kind']=='orientation'),None)
        edges=orientation.get('edges',[]) if orientation else []
        self.conflict_edge_choice.blockSignals(True)
        current=self.conflict_edge_choice.currentIndex()
        if self.conflict_edge_choice.count()!=len(edges):
            self.conflict_edge_choice.clear()
            for i,edge in enumerate(edges):self.conflict_edge_choice.addItem(f'冲突边 {i+1}/{len(edges)}：{tuple(edge)}')
            current=0
        self.conflict_edge_choice.setCurrentIndex(max(0,current));self.conflict_edge_choice.setVisible(bool(edges));self.conflict_edge_choice.blockSignals(False)
        if edges:
            index=max(0,self.conflict_edge_choice.currentIndex());selected=[{**x,'edges':[edges[index]]} if x['kind']=='orientation' else x for x in selected]
        self.selection_help.setText('\n'.join(x['description'] for x in selected) or '点击诊断项查看含义；可选中对象后点击“定位并放大”。边界不自动等于缺损。')
        if hasattr(self.viewer,'highlight_diagnostics'):
            self.viewer.highlight_diagnostics(self.display_asset(),selected)
        else:
            self.viewer.highlight(self.display_asset(),sorted({i for x in selected for i in x['faces']}),
                                  [e for x in selected for e in x.get('edges',[])])

    def repair(self):
        try:
            ids=[int(x.strip()) for x in self.delete_ids.text().split(",") if x.strip()]
            split_ids=[int(x.strip()) for x in self.split_ids.text().split(',') if x.strip()]
        except ValueError:
            self.log.appendPlainText("删除面索引必须是逗号分隔的整数");return
        roles=self.boundary_roles.mapping(self.asset,self.diagnosis)
        if self.hole_method.currentData() in ('quadric','surface'):self.self_check.setChecked(True)
        self.start_job("repair",parameters={"remove_duplicates":self.clean_duplicates.isChecked(),
                       "hole_method":self.hole_method.currentData(),
                       "remove_degenerate":self.clean_degenerate.isChecked(),"orient_faces":self.orient.isChecked(),
                       "fill_boundary_ids":[int(bid) for bid,role in roles.items() if role=='repair_target'],
                       "boundary_roles":roles,
                       "delete_face_ids":ids,"split_vertex_ids":split_ids,"max_hole_span":self.hole_span.value(),
                       "check_self_intersection":self.self_check.isChecked()})

    def selection_changed(self):
        self.highlight()
        self._selection_description=self.selection_help.text()
        if self.auto_focus.isChecked():self.focus_selected()

    def mark_boundary_role(self):
        if self.asset is None or self.pending_review or self.process is not None:return
        ids={x.data(256)['boundary'] for x in self.defects.selectedItems() if 'boundary' in x.data(256)}
        boundaries=[b for b in self.diagnosis['boundaries'] if b['id'] in ids]
        if not boundaries:
            self.log.appendPlainText('请先选中一个或多个边界。');return
        try:
            self.boundary_roles.mark(self.asset,boundaries,self.boundary_role.currentData())
            self.bind_diagnosis(self.diagnosis)
        except ValueError as error:self.log.appendPlainText(str(error))

    def request_suggestions(self):
        if self.asset is not None and self.diagnosis:
            self.suggestion_status.setText('正在后台搜索并复检候选；结束后这里显示方案数量和下一步。')
            self.start_job('suggest',parameters={'boundary_roles':self.boundary_roles.mapping(self.asset,self.diagnosis),
                                                'max_candidates':self.suggestion_budget.value()})

    def set_boundary_role(self,boundary,role):
        if self.pending_review or self.process is not None:return
        self.boundary_roles.mark(self.asset,[boundary],role);self.bind_diagnosis(self.diagnosis)

    def suggest_boundary_roles(self):
        if self.asset is None or self.pending_review or self.process is not None:return
        from .boundary_advice import boundary_advice
        advice=boundary_advice(self.asset,self.diagnosis['boundaries']);self._boundary_advice=advice
        # Recommendations never change roles or trigger repair automatically.
        for row,item in enumerate(advice):
            cell=self.boundary_table.item(row,0);cell.setToolTip(item['reason']);cell.setText(f"边界 {item['id']} · "+('建议补小孔' if item['role']=='repair_target' else '需人工判断'))
        self.boundary_advice_text.setText('；'.join(f"边界 {x['id']}：{x['reason']}" for x in advice) or '当前没有边界。')
        self.controls_scroll.ensureWidgetVisible(self.boundary_table)

    def confirm_boundary_advice(self):
        if self.asset is None or self.pending_review or self.process is not None:return
        from .boundary_advice import boundary_advice
        roles=self.boundary_roles.mapping(self.asset,self.diagnosis)
        advice=boundary_advice(self.asset,self.diagnosis['boundaries'])
        targets={x['id'] for x in advice if x['role']=='repair_target' and roles[str(x['id'])]=='uncertain'}
        self.boundary_roles.mark(self.asset,[b for b in self.diagnosis['boundaries'] if b['id'] in targets],'repair_target')
        self.bind_diagnosis(self.diagnosis);self.boundary_advice_text.setText(f'已确认 {len(targets)} 个小孔目标；原有天然开口标记未修改。请生成预览检查。')

    def apply_suggestion(self):
        if self.pending_review or self.process is not None or self.asset is None:return
        index=self.suggestion_choice.currentIndex()-1
        if self.suggestions_version!=self.asset.version or not 0<=index<len(self.suggestions):return
        proposal=self.suggestions[index]
        self.self_check.setChecked(True)
        self.delete_ids.setText(','.join(map(str,proposal['delete_face_ids'])))
        self.split_ids.setText(','.join(map(str,proposal.get('split_vertex_ids',[]))))
        self.selection_help.setText(proposal['explanation']+
            f"\n边界环 {proposal['boundary_loops_before']} → {proposal['boundary_loops_after']}；"
            f"连通分量 {proposal['components_before']} → {proposal['components_after']}。\n请生成修复预览后再决定是否接受。")
        if proposal['boundary_loops_after']>proposal['boundary_loops_before']:
            self.selection_help.setText(self.selection_help.text()+'\n注意：该方案新增了开口，只能说明异常拓扑减少，不代表已恢复完整闭合模型。请比较其他方案或明确后续补洞目标。')
        entry=dict(kind='candidate',faces=proposal['delete_face_ids'] or proposal.get('affected_face_ids',[]),edges=[],vertices=proposal.get('split_vertex_ids',[]))
        if hasattr(self.viewer,'highlight_diagnostics'):
            self.viewer.highlight_diagnostics(self.asset,[entry])
            if hasattr(self.viewer,'focus_selection'):self.viewer.focus_selection(self.asset)

    def focus_selected(self,manual=False):
        if self.asset is not None and hasattr(self.viewer,'focus_selection'):
            self.viewer.focus_selection(self.display_asset(),zoom=.75 if manual else 1.)
            if getattr(self.viewer,'local_view',False):
                note='局部视图：仅显示附近表面以避免背面遮挡；裁切外缘不是检测到的缺陷。点击“恢复全貌”返回。'
                base=getattr(self,'_selection_description',self.selection_help.text().split('\n局部视图：')[0])
                self.selection_help.setText(base+'\n'+note)

    def show_overview(self):
        if hasattr(self.viewer,'overview'):self.viewer.overview()
        self.highlight()

    def accept_preview(self):
        if not self.pending_review:return
        review=self.pending_review
        if self.asset.version!=review.input_asset.version:
            self.log.appendPlainText('当前输入版本已改变，不能接受此预览。');return
        # Persist the snapshot before accepting its review decision.
        self.store.commit(review.candidate,review.result)
        self.asset=review.resolve(self.asset,True)
        self.redo_stack.clear()
        (self.store.root/(self.asset.version+'.review.json')).write_bytes((review.output_dir/'review.json').read_bytes())
        self.accepted_diagnosis=review.result['diagnosis_after']
        self.pending_review=None
        self.bind_diagnosis(self.accepted_diagnosis);self.render();self._busy(False)
        self.review_summary.setText('已接受修复版本。可导出，或回退上一版本。')
        self.patch_summary.setText('已接受版本。补片质量及变化面记录保存在本次任务结果中。')
        self.asset_changed.emit(self.asset)

        self.review_resolved.emit(dict(decision='accepted',directory=str(review.output_dir)))

    def discard_preview(self):
        if not self.pending_review:return
        review=self.pending_review
        self.asset=review.resolve(self.asset,False)
        self.accepted_diagnosis=review.result['diagnosis_before']
        self.pending_review=None
        self.bind_diagnosis(self.accepted_diagnosis);self.render();self._busy(False)
        self.review_summary.setText('已放弃预览，保留输入版本。')
        self.patch_summary.setText('已放弃预览，补片没有提交。')
        self.review_resolved.emit(dict(decision='discarded',directory=str(review.output_dir)))

    def change_view(self,index):
        if hasattr(self.viewer,'set_view'):self.viewer.set_view(index)

    def change_opacity(self,value):
        if hasattr(self.viewer,'set_opacity'):self.viewer.set_opacity(value/100)

    def enable_boundary_picking(self,enabled):
        if hasattr(self.viewer,'enable_boundary_picking'):
            self.viewer.enable_boundary_picking(self.select_boundary_at if enabled else None)
            self.display_info.setText(getattr(self.viewer,'display_notice',''))

    def select_boundary_at(self,point):
        if self.process is not None or self.asset is None or not self.diagnosis:return
        bid=nearest_boundary(self.display_asset(),self.diagnosis,point)
        if bid is None:
            self.log.appendPlainText('点击位置不在已检测到的孔边附近。');return
        self.defects.clearSelection()
        for i in range(self.defects.count()):
            item=self.defects.item(i)
            if item.data(256).get('boundary')==bid:
                item.setSelected(True);self.defects.scrollToItem(item);break

    def save_snapshot(self):
        if self.asset is None:return
        path,_=QFileDialog.getSaveFileName(self,'保存当前观察视图','model_view.png','PNG (*.png)')
        if path and hasattr(self.viewer,'save_snapshot'):
            self.viewer.save_snapshot(path)
            metadata={'input_version':self.asset.version,'display_version':self.display_asset().version,
                      'boundary_roles':self.boundary_roles.mapping(self.display_asset(),self.diagnosis),
                      'paired_comparison':self.pending_review is not None and self.dual_view.isChecked(),
                      'show_changes':self.pending_review is not None and self.show_changes.isChecked(),
                      'is_unaccepted_preview':self.pending_review is not None,'opacity':self.opacity.value()/100,
                      'wireframe':self.wire.isChecked(),'local_view':getattr(self.viewer,'local_view',False)}
            Path(path+'.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')

    def rollback(self):
        try:
            if self.process is not None or self.pending_review:raise ValueError('请先完成任务或处理待接受预览')
            previous=self.asset.version;self.asset=self.store.rollback();self.redo_stack.append(previous);self.diagnosis=None;self.accepted_diagnosis=None;self.defects.clear()
            self.asset_changed.emit(self.asset);self.render();self.start_job("diagnose")
        except Exception as e:self.log.appendPlainText(str(e))

    def redo(self):
        try:
            if self.process is not None or self.pending_review or not self.redo_stack:raise ValueError('当前没有可重做的版本')
            self.asset=self.store.redo(self.redo_stack[-1]);self.redo_stack.pop();self.diagnosis=None;self.accepted_diagnosis=None;self.defects.clear()
            self.asset_changed.emit(self.asset);self.render();self.start_job('diagnose')
        except Exception as e:self.log.appendPlainText(str(e))

    def export(self):
        if self.asset is None or self.process is not None or self.pending_review is not None:
            self.export_finished.emit(dict(status='failed',errors=['请先完成任务并接受或放弃预览，再导出当前正式版本。']));return
        info=export_summary(self.asset)
        title=f"导出已接受版本｜单位：{info['unit']}｜尺寸："+' × '.join(f'{x:.4g}' for x in info['dimensions'])
        path,_=QFileDialog.getSaveFileName(self,title,"model.m3d","完整项目包 (*.m3d);;STL (*.stl);;分壳STL集合 (*.stlset.zip);;NPZ (*.npz)")
        if path:
            try:
                if path.lower().endswith('.stlset.zip'):
                    from ..io.shell_set import save_shell_set
                    manifest=save_shell_set(self.asset,path)
                    self.log.appendPlainText(f"已导出{len(manifest['shells'])}个独立壳体："+path)
                    self.log.appendPlainText(manifest['warning']);self.export_finished.emit(dict(status='completed',path=path,warnings=[manifest['warning']]));return
                if Path(path).suffix.lower()=='.m3d':
                    save_project(path,self.asset,self.diagnosis,self.boundary_roles.mapping(self.asset,self.diagnosis),self.store)
                    self.log.appendPlainText('已导出完整项目包：'+path);self.export_finished.emit(dict(status='completed',path=path,warnings=[]));return
                save_mesh(self.asset,path)
                if Path(path).suffix.lower()=='.stl':
                    audit=json.loads(Path(path+'.json').read_text(encoding='utf-8'))['export_validation']
                    for warning in audit['warnings']:self.log.appendPlainText('导出检查：'+warning)
                annotations={'version':self.asset.version,'geometry_hash':self.asset.geometry_hash(),
                             'boundary_roles':self.boundary_roles.mapping(self.asset,self.diagnosis)}
                Path(path+'.boundary_roles.json').write_text(json.dumps(annotations,ensure_ascii=False,indent=2),encoding='utf-8')
                self.log.appendPlainText("已导出："+path)
                self.export_finished.emit(dict(status='completed',path=path,warnings=audit['warnings'] if Path(path).suffix.lower()=='.stl' else []))
            except Exception as e:
                self.log.appendPlainText(str(e));self.export_finished.emit(dict(status='failed',path=path,errors=[str(e)]))
