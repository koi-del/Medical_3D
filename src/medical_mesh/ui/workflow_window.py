"""One workflow with fixed canvas, task settings and shared result review."""
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QSize,QUrl
from PySide6.QtWidgets import (QApplication,QMainWindow,QStackedWidget,QPushButton,QLabel,QVBoxLayout,
    QHBoxLayout,QWidget,QSplitter,QTabWidget,QToolButton,QButtonGroup,QScrollArea,QComboBox,
    QLineEdit,QFileDialog,QSpinBox,QFormLayout,QStyle,QSizePolicy,QLayout,QTreeWidget,QTreeWidgetItem,QMenu,QCheckBox,QDoubleSpinBox)
from PySide6.QtGui import QAction,QDesktopServices,QColor,QBrush,QPixmap
from ..integration.member2 import to_optimization,from_optimization
from ..member2.core.model import save_asset
from ..io.mesh_io import save_mesh,load_mesh
from ..member2.ui.main_window import MainWindow as NumericalWorkbench
from .member1_panel import Member1Panel
from .preview_host import ViewerAdapter
from .glass_theme import GlassBackground,OpticalGlass,glass_card,STYLE
from .technical_icons import technical_icon
from .sidebar import Sidebar
from .object_panel import ObjectPanel,version_of
from .feedback import explain_reasons
from .branding import LOGO_PATH,project_icon,configure_application_identity


class Workbench(QMainWindow):
    steps=('repair','optimize','evaluate','export')

    def __init__(self,root=None,session_root=None,off_screen=False):
        super().__init__();self.root=Path(root or Path(__file__).resolve().parents[3]);self._review_requested=False;self.last_feedback=''
        self.setWindowTitle('医学三维网格工作台');self.resize(1480,940)
        self.setWindowIcon(project_icon())
        self.viewer=ViewerAdapter(self);self.repair=Member1Panel(self.viewer,session_root or self.root/'results/gui_session',self)
        self.numerical=NumericalWorkbench(self.root,off_screen=off_screen);self.numerical.setParent(self,Qt.Widget)
        r=self.repair;n=self.numerical;n.diagnostic_provider='medical_mesh.integration.member2:diagnose_pair';self.current_step='repair'
        central=GlassBackground();layout=QVBoxLayout(central);layout.setContentsMargins(2,2,2,2);layout.setSpacing(2);self.setCentralWidget(central)
        header=QHBoxLayout();brand=QLabel();brand.setObjectName('projectLogo');brand.setFixedSize(44,36);brand.setAlignment(Qt.AlignCenter)
        brand.setPixmap(QPixmap(str(LOGO_PATH)).scaled(44,36,Qt.KeepAspectRatio,Qt.SmoothTransformation));brand.setToolTip('医学三维工作台');header.addWidget(brand)
        titles=QVBoxLayout();titles.setSpacing(1);heading=QLabel('医学三维工作台');heading.setObjectName('brand');titles.addWidget(heading)
        subtitle=QLabel('MEDICAL MESH  /  三维模型处理与格式适配');subtitle.setObjectName('subtitle');subtitle.hide();titles.addWidget(subtitle);header.addLayout(titles);header.addSpacing(22)
        self.model_name=QLabel('尚未打开模型');self.model_name.setObjectName('modelName');self._asset_id=None
        self.state_badge=QLabel('尚未打开模型');self.state_badge.setMinimumWidth(200);self.state_badge.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.state_badge.setObjectName('stateBadge');header.addWidget(self.model_name);header.addStretch();header.addWidget(self.state_badge);layout.addLayout(header)
        ribbon=glass_card(OpticalGlass(),'ribbon');ribbon_layout=QVBoxLayout(ribbon);ribbon_layout.setContentsMargins(7,0,7,3);ribbon_layout.setSpacing(3)
        toolbar=QHBoxLayout();r.import_button.setText('打开模型 / 项目');r.undo_button.setText('回退上一版本');r.export_button.setText('保存项目 / 导出网格')
        for widget in (r.import_button,QLabel('导入单位'),r.units,r.diagnose_button,r.undo_button):toolbar.addWidget(widget)
        toolbar.addStretch();toolbar.addWidget(n.history_button);toolbar.addWidget(r.export_button)
        self.redo_button=QPushButton('重做版本');self.redo_button.setIcon(technical_icon(QStyle.SP_ArrowBack));self.redo_button.clicked.connect(r.redo);toolbar.insertWidget(5,self.redo_button)
        self.before_after_button=QPushButton('对照接受前 / 后');self.before_after_button.clicked.connect(self.show_accepted_comparison);toolbar.addWidget(self.before_after_button)
        for widget,icon in ((r.import_button,QStyle.SP_DialogOpenButton),(r.diagnose_button,QStyle.SP_BrowserReload),(r.undo_button,QStyle.SP_ArrowBack),(n.history_button,QStyle.SP_FileDialogDetailedView),(r.export_button,QStyle.SP_DialogSaveButton)):
            widget.setIcon(self.style().standardIcon(icon))
        r.import_button.setObjectName('primaryAction');r.accept_button.setObjectName('acceptAction');r.summary.setObjectName('summaryStrip')
        n.history_button.clicked.connect(lambda:self._update_metric_summary(n.last_result))
        self.limits_explanation=QLabel();self.limits_explanation.setWordWrap(True);n.optimization_form.addRow(self.limits_explanation)
        self.search_explanation=QLabel('九候选＝80%、50%、30%保留率，各搭配0、5、10次Taubin平滑，共9组。它不使用上面的单一目标；单击行观察，双击合格行进入待接受预览。');self.search_explanation.setWordWrap(True);n.optimization_form.addRow(self.search_explanation)
        n.search.setToolTip(self.search_explanation.text())
        navigation=QHBoxLayout();navigation.setSpacing(3);navigation.setContentsMargins(0,2,0,0);self.navigation=QButtonGroup(self);self.step_buttons={}
        for index,(key,label) in enumerate(zip(self.steps,('检查与修复','简化与平滑','误差与对比','格式与导出'))):
            button=QToolButton();button.setText(label);button.setCheckable(True);button.setFixedSize(116,30);button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setObjectName('stepTab')
            self.navigation.addButton(button,index);navigation.addWidget(button);self.step_buttons[key]=button
        navigation.addStretch();ribbon_layout.addLayout(navigation);ribbon_layout.addLayout(toolbar)
        self.command_strip=QHBoxLayout();self.command_strip.setSpacing(0);ribbon_layout.addLayout(self.command_strip)
        self._ribbon_actions=[]
        def group(title,actions):
            box=QWidget();box.setObjectName('ribbonGroup');column=QVBoxLayout(box);column.setContentsMargins(7,2,7,0);column.setSpacing(1);row=QHBoxLayout();row.setSpacing(3)
            for label,icon,callback,source in actions:
                button=QToolButton();button.setObjectName('ribbonCommand');button.setText(label);button.setToolTip(label.replace('\n',''));button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setIcon(technical_icon(icon));button.setIconSize(QSize(32,32));button.clicked.connect(callback);row.addWidget(button)
                if source:self._ribbon_actions.append((button,source))
            column.addLayout(row);caption=QLabel(title);caption.setObjectName('groupCaption');caption.setAlignment(Qt.AlignCenter);column.addWidget(caption);self.command_strip.addWidget(box)
        group('项目与数据', [('打开模型',QStyle.SP_DialogOpenButton,r.import_button.click,r.import_button),('保存 / 导出',QStyle.SP_DialogSaveButton,r.export_button.click,r.export_button),('任务记录',QStyle.SP_FileDialogDetailedView,n.history_button.click,n.history_button)])
        group('网格诊断与版本',[('重新检测',QStyle.SP_BrowserReload,r.diagnose_button.click,r.diagnose_button),('回退版本',QStyle.SP_ArrowBack,r.undo_button.click,r.undo_button)])
        group('处理与分析',[('检查修复',QStyle.SP_FileDialogContentsView,lambda:self.set_step('repair'),None),('简化平滑',QStyle.SP_ComputerIcon,lambda:self.set_step('optimize'),None),('误差分析',QStyle.SP_FileDialogInfoView,lambda:self.set_step('evaluate'),None),('格式转换',QStyle.SP_DriveHDIcon,lambda:self.set_step('export'),None)])
        group('视图控制',[('适合窗口',QStyle.SP_TitleBarMaxButton,self.fit_view,None),('保存视图',QStyle.SP_DesktopIcon,self.save_snapshot,None)])
        self.command_strip.addStretch();layout.addWidget(ribbon);self.navigation.idClicked.connect(lambda i:self.set_step(self.steps[i]))
        self.sidebar_menu=QMenu(self);sidebar_menu_button=QToolButton();sidebar_menu_button.setText('侧栏 ▾');sidebar_menu_button.setMenu(self.sidebar_menu);sidebar_menu_button.setPopupMode(QToolButton.InstantPopup);toolbar.addWidget(sidebar_menu_button)
        split=QSplitter();self.settings=QStackedWidget();self.settings.setMinimumWidth(245);self.settings.setMaximumWidth(380)
        self.settings.addWidget(r.controls_scroll)
        r.self_check.setChecked(True)
        r.controls_scroll.widget().layout().insertWidget(0,r.pick_boundary)
        r.controls_scroll.widget().layout().insertWidget(1,r.self_check)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(n.pages['optimization']);self.settings.addWidget(scroll)
        self.settings.addWidget(self._evaluation_settings())
        export_page=QWidget();export_layout=QVBoxLayout(export_page)
        native=QPushButton('导出当前正式模型 / 完整项目');native.clicked.connect(r.export);export_layout.addWidget(native)
        export_layout.addWidget(r.export_info);export_layout.addWidget(n.cad);n.cad.mode.setCurrentIndex(1);self.settings.addWidget(export_page)
        settings_card=glass_card(OpticalGlass(),'settingsCard');settings_layout=QVBoxLayout(settings_card);settings_layout.setContentsMargins(8,7,8,5)
        self.settings_title=QLabel('检查与修复');self.settings_title.setObjectName('sectionTitle');settings_layout.addWidget(self.settings_title)
        self.settings_hint=QLabel('诊断网格 · 定位问题 · 受控修复');self.settings_hint.setObjectName('sectionHint');settings_layout.addWidget(self.settings_hint);settings_layout.addWidget(self.settings)
        settings_card.setMinimumWidth(255);settings_card.setMaximumWidth(390)
        canvas=glass_card(OpticalGlass(),'canvasCard');canvas_layout=QVBoxLayout(canvas);canvas_layout.setContentsMargins(3,3,3,1);view_tools=QHBoxLayout();view_tools.setSpacing(5)
        for widget in (QLabel('视角'),r.view_preset,r.wire,QLabel('不透明度'),r.opacity):view_tools.addWidget(widget)
        r.opacity.setMaximumWidth(85);r.overview_button.setText('全貌');r.snapshot_button.setText('截图')
        self.color_mode=QComboBox()
        for label,key in [('误差色图','surface'),('实体颜色','solid'),('原始采样点','points')]:self.color_mode.addItem(label,key)
        self.color_mode.currentIndexChanged.connect(lambda _:n.viewer.set_error_mode(self.color_mode.currentData()))
        view_tools.addWidget(self.color_mode);view_tools.addWidget(r.overview_button);view_tools.addWidget(r.snapshot_button);view_tools.addStretch();canvas_layout.addLayout(view_tools)
        preview_tools=QHBoxLayout();preview_tools.addWidget(r.dual_view);preview_tools.addWidget(r.show_changes)
        self.preview_legend=QLabel('绿色：新增面 · 红色：删除面 · 橙色：翻面 · 黄色：边界 · 紫色：退化/异常点');self.preview_legend.setWordWrap(True);preview_tools.addWidget(self.preview_legend,1);canvas_layout.addLayout(preview_tools)
        self.viewport=QStackedWidget();self.viewport.addWidget(self.viewer.interactor);self.viewport.addWidget(n.viewer);canvas_layout.addWidget(self.viewport,1)
        self.view_identity=QLabel('当前操作模型：尚未打开');self.view_identity.setTextInteractionFlags(Qt.TextSelectableByMouse);canvas_layout.insertWidget(2,self.view_identity)
        self.canvas_notice=QLabel('打开模型后，按上方流程处理；未接受的结果不会替换当前模型。');self.canvas_notice.setObjectName('canvasNotice');self.canvas_notice.setWordWrap(True)
        canvas_layout.addWidget(self.canvas_notice)
        rail=QWidget();rail.setObjectName('viewRail');rail.setFixedWidth(54);rail_layout=QVBoxLayout(rail);rail_layout.setContentsMargins(2,5,2,5);rail_layout.setSpacing(4)
        for label,icon,callback in [('全貌',QStyle.SP_TitleBarMaxButton,self.fit_view),('等轴',QStyle.SP_ComputerIcon,lambda:self.change_view(0)),('正面',QStyle.SP_ArrowUp,lambda:self.change_view(1)),('侧面',QStyle.SP_ArrowRight,lambda:self.change_view(2)),('顶部',QStyle.SP_ArrowDown,lambda:self.change_view(3)),('线框',QStyle.SP_FileDialogListView,r.wire.toggle),('截图',QStyle.SP_DesktopIcon,self.save_snapshot)]:
            tool=QToolButton();tool.setObjectName('railCommand');tool.setText(label);tool.setIcon(technical_icon(icon));tool.setIconSize(QSize(24,24));tool.setToolButtonStyle(Qt.ToolButtonTextUnderIcon);tool.clicked.connect(callback);rail_layout.addWidget(tool)
        rail_layout.addStretch();left_content=QWidget();left_layout=QHBoxLayout(left_content);left_layout.setContentsMargins(0,0,0,0);left_layout.setSpacing(2);left_layout.addWidget(rail);left_layout.addWidget(settings_card,1)
        self.left_sidebar=Sidebar('操作工具与参数',left_content,'left',330,440);split.addWidget(self.left_sidebar);split.addWidget(canvas)
        self.inspector=glass_card(QTabWidget(),'inspectorCard');self.inspector.setMinimumWidth(0);self.inspector.setMaximumWidth(16777215)
        quality=QWidget();quality_layout=QHBoxLayout(quality);quality_layout.setContentsMargins(8,5,8,5);quality_layout.setSpacing(14)
        review_column=QWidget();review_layout=QVBoxLayout(review_column);review_layout.setContentsMargins(0,0,0,0)
        for widget in (r.review_summary,r.change_legend):review_layout.addWidget(widget)
        review_layout.addStretch();quality_layout.addWidget(review_column,2)
        metric_column=QWidget();metric_layout=QVBoxLayout(metric_column);metric_layout.setContentsMargins(0,0,0,0);metric_layout.addWidget(r.patch_summary)
        self.metric_summary=QLabel('处理结果、误差和候选方案显示在这里。');self.metric_summary.setWordWrap(True);metric_layout.addWidget(self.metric_summary);metric_layout.addStretch();quality_layout.addWidget(metric_column,2)
        n.table.setMaximumHeight(340);n.table.setMinimumHeight(105);quality_layout.addWidget(n.table,3)
        n.table.setColumnHidden(3,False);n.table.setColumnHidden(5,False)
        n.table.cellDoubleClicked.connect(lambda *_:self.review_optimization())
        n.table.setToolTip('单击一行观察该候选；双击通过筛选的行，或点击底部“预览所选优化方案”，进入接受/放弃预览。未通过方案只能检查原因。')
        quality_scroll=QScrollArea();quality_scroll.setWidgetResizable(True);quality_scroll.setWidget(quality)
        r.patch_summary.setMinimumHeight(0)
        self.inspector.addTab(quality_scroll,'结果与质量');self.inspector.addTab(n.report_viewer,'报告');self.inspector.addTab(n.conversion_results,'转换记录')
        dock=QWidget();dock.setObjectName('propertyDock');dock.setMinimumWidth(300);dock.setMaximumWidth(410);dock_layout=QVBoxLayout(dock);dock_layout.setContentsMargins(0,0,0,0);dock_layout.setSpacing(0)
        scene=QWidget();scene_layout=QVBoxLayout(scene);scene_layout.setContentsMargins(0,0,0,0);scene_title=QLabel('  模型管理');scene_title.setObjectName('dockTitle');scene_layout.addWidget(scene_title)
        self.objects=ObjectPanel();self.scene_tree=self.objects.tree;self.objects.display_changed.connect(lambda:self.apply_object_display(force=True));scene_layout.addWidget(self.objects)
        dock_layout.addWidget(scene,1)
        self.right_sidebar=Sidebar('模型与属性',dock,'right',320,430);split.addWidget(self.right_sidebar);split.setStretchFactor(1,1);split.setSizes([345,850,325])
        self.work_area=QSplitter(Qt.Vertical);self.work_area.addWidget(split)
        self.results_panel=QWidget();results_layout=QVBoxLayout(self.results_panel);results_layout.setContentsMargins(0,0,0,0);results_layout.setSpacing(0)
        results_header=QHBoxLayout();results_title=QLabel('  处理结果与质量报告');results_title.setObjectName('dockTitle');results_header.addWidget(results_title,1)
        close_results=QToolButton();close_results.setText('×');close_results.setToolTip('收起结果区域');close_results.clicked.connect(lambda:self.results_toggle.setChecked(False));results_header.addWidget(close_results);results_layout.addLayout(results_header);results_layout.addWidget(self.inspector)
        self.work_area.addWidget(self.results_panel);self.work_area.setStretchFactor(0,1);self.work_area.setSizes([620,220]);layout.addWidget(self.work_area,1)
        self.results_toggle=QToolButton();self.results_toggle.setText('结果与报告');self.results_toggle.setCheckable(True);self.results_toggle.toggled.connect(self.results_panel.setVisible);toolbar.addWidget(self.results_toggle);self.results_panel.hide()
        self.sidebar_actions={}
        for name,sidebar in [('左侧操作工具与参数',self.left_sidebar),('右侧模型与属性',self.right_sidebar)]:
            action=QAction(name,self);action.setCheckable(True);action.setChecked(True);action.toggled.connect(sidebar.set_open);sidebar.open_changed.connect(action.setChecked);self.sidebar_menu.addAction(action);self.sidebar_actions[name]=action
        self.sidebar_menu.addSeparator();restore=QAction('恢复两侧栏',self);restore.triggered.connect(lambda:[side.set_open(True) for side in (self.left_sidebar,self.right_sidebar)]);self.sidebar_menu.addAction(restore)
        layout.addWidget(r.summary)
        feedback_row=QHBoxLayout();self.feedback=QLabel('就绪：打开模型后，可在右侧管理显示对象。');self.feedback.setWordWrap(True);self.feedback.setTextInteractionFlags(Qt.TextSelectableByMouse);feedback_row.addWidget(self.feedback,1)
        self.result_folder=None;self.folder_button=QPushButton('打开结果目录');self.folder_button.setEnabled(False);self.folder_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result_folder))) if self.result_folder else None);feedback_row.addWidget(self.folder_button);layout.addLayout(feedback_row)
        self.stage_button=QPushButton('预览所选优化方案');self.stage_button.clicked.connect(self.review_optimization)
        footer=QHBoxLayout();footer.addWidget(r.review_banner,1);r.preview_side.setItemText(0,'观察处理后预览');r.preview_side.setItemText(1,'观察当前输入')
        for widget in (self.stage_button,r.preview_side,r.accept_button,r.discard_button):footer.addWidget(widget)
        review_card=glass_card(OpticalGlass(),'reviewCard');review_card.setLayout(footer);footer.setContentsMargins(7,3,7,3);layout.addWidget(review_card)
        status=QHBoxLayout();self.status=QLabel('就绪');status.addWidget(self.status,1);status.addWidget(r.task_progress)
        self.cancel_button=QPushButton('取消当前任务');self.cancel_button.clicked.connect(self.cancel_current);status.addWidget(self.cancel_button)
        self.log_toggle=QToolButton();self.log_toggle.setText('运行记录');self.log_toggle.setCheckable(True);status.addWidget(self.log_toggle);layout.addLayout(status)
        self.logs=QTabWidget();self.logs.setMaximumHeight(150);self.logs.addTab(r.log,'处理记录');self.logs.addTab(n.log,'计算记录');layout.addWidget(self.logs);self.logs.hide();self.log_toggle.toggled.connect(self.logs.setVisible)
        self.setStyleSheet(STYLE)
        r.summary.setMinimumHeight(r.fontMetrics().lineSpacing()*2+14)
        for form in self.settings.findChildren(QFormLayout):form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        for field in self.settings.findChildren(QLineEdit)+self.settings.findChildren(QComboBox):
            field.setMinimumWidth(0);field.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        for area in self.settings.findChildren(QScrollArea)+[r.controls_scroll]:
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            content=area.widget()
            if content:
                content.setMinimumWidth(0);content.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
                if content.layout():content.layout().setSizeConstraint(QLayout.SetNoConstraint)
        for plotter in (self.viewer.plotter,self.viewer.other_plotter,n.viewer.plotter):plotter.set_background('#dadada',top='#808080')
        r.hide();n.hide();n.workspace.setCurrentWidget=self._route_workspace
        r.view_preset.currentIndexChanged.disconnect();r.view_preset.currentIndexChanged.connect(self.change_view)
        r.opacity.valueChanged.disconnect();r.opacity.valueChanged.connect(self.change_opacity)
        r.wire.toggled.disconnect();r.wire.toggled.connect(self.change_wire)
        r.snapshot_button.clicked.disconnect();r.snapshot_button.clicked.connect(self.save_snapshot)
        r.overview_button.clicked.disconnect();r.overview_button.clicked.connect(self.fit_view)
        r.asset_changed.connect(self.sync_reference);r.diagnosis_changed.connect(lambda _:self.sync_reference());r.preview_changed.connect(lambda _:self._show_pending())
        r.task_finished.connect(self._repair_finished);r.export_finished.connect(self._export_finished)
        r.review_resolved.connect(self._review_resolved)
        r.accept_button.clicked.connect(lambda:self.notify('已接受预览，正式版本已更新；可继续处理、导出或回退。','success'))
        r.discard_button.clicked.connect(lambda:self.notify('已放弃预览，保留原模型。','info'))
        n.jobs.finished.connect(self._numerical_finished);n.table.cellClicked.connect(lambda *_:self._update_metric_summary())
        n.jobs.busy_changed.connect(self._numerical_busy)
        r.focus_button.clicked.connect(lambda:self._set_viewport(0))
        self.refresh_timer=QTimer(self);self.refresh_timer.timeout.connect(self.refresh_state);self.refresh_timer.start(200);self.set_step('repair');self.refresh_state()

    def _evaluation_settings(self):
        page=QWidget();form=QFormLayout(page)
        hint=QLabel('当前模型作为参考。可观察优化结果，或选择另一模型计算双向误差；评价不会替换模型。');hint.setWordWrap(True);form.addRow(hint)
        self.evaluation_path=QLineEdit();self.evaluation_path.setPlaceholderText('选择用于比较的 STL / NPZ / PLY / OBJ')
        self.evaluation_path.textChanged.connect(self.clear_external_evaluation)
        browse=QPushButton('选择对比模型');browse.clicked.connect(self.choose_evaluation_file);form.addRow(self.evaluation_path);form.addRow(browse)
        self.evaluation_unit=QComboBox();self.evaluation_unit.addItems(['使用文件元数据（不猜单位）','mm','cm','m']);form.addRow('对比文件单位',self.evaluation_unit)
        self.evaluation_samples=QSpinBox();self.evaluation_samples.setRange(1000,100000);self.evaluation_samples.setValue(50000);form.addRow('每方向采样',self.evaluation_samples)
        self.evaluate_button=QPushButton('计算双向误差');self.evaluate_button.clicked.connect(self.evaluate_external);form.addRow(self.evaluate_button)
        self.observe_candidate_button=QPushButton('观察所选优化候选');self.observe_candidate_button.clicked.connect(self.show_optimization_result);form.addRow(self.observe_candidate_button)
        note=QLabel('D95与最大偏差基于有限采样，不是精确Hausdorff。不同已知单位会生成换算副本，原模型不变。');note.setWordWrap(True);form.addRow(note);return page

    def _route_workspace(self,widget):
        n=self.numerical
        if widget in (n.report_viewer,n.conversion_results):self.show_results()
        if widget is n.report_viewer:self.inspector.setCurrentIndex(1)
        elif widget is n.conversion_results:self.inspector.setCurrentIndex(2)
        elif widget is n.viewer and self.repair.pending_review is None:self._set_viewport(1)

    def _set_viewport(self,index):
        if self.viewport.currentIndex()==index:return
        matched=bool(self.repair.asset and self.numerical.viewer.assets.get(0) and self.numerical.viewer.assets[0].asset_id==self.repair.asset.asset_id)
        source=self.viewer.plotter if self.viewport.currentIndex()==0 else self.numerical.viewer.plotter
        position=source.camera_position if matched else None
        self.viewport.setCurrentIndex(index)
        if position is not None:
            target=self.viewer.plotter if index==0 else self.numerical.viewer.plotter
            target.camera_position=position;target.reset_camera_clipping_range();target.render()

    def set_step(self,step):
        if step not in self.steps:raise ValueError('Unknown workflow step')
        self.current_step=step;self.settings.setCurrentIndex(self.steps.index(step));self.step_buttons[step].setChecked(True)
        titles={'repair':('检查与修复','诊断网格 · 定位问题 · 受控修复'),'optimize':('简化与平滑','设置目标 · 生成方案 · 预览接受'),'evaluate':('误差与对比','独立评价 · 双向误差 · 质量复核'),'export':('格式与导出','正式版本 · 格式转换 · 独立回读')}
        self.settings_title.setText(titles[step][0]);self.settings_hint.setText(titles[step][1])
        self.left_sidebar.set_open(True)
        if self.repair.pending_review:self._show_pending()
        else:self._set_viewport(0 if step in ('repair','export') else 1)
        if step=='export':self.numerical.cad.show();self.repair.export_info.show()
        self.refresh_state()

    def sync_reference(self,*_):
        asset=self.repair.asset;n=self.numerical
        if asset is None or n.jobs.busy:return
        identity=(asset.version,getattr(self.repair,'loaded_source',asset.source_file))
        if self._asset_id!=identity:
            old=getattr(self,'_last_formal_asset',None)
            source=identity[1]
            self.previous_asset=old if old and asset.parent_version==old.version and source==getattr(self,'_last_formal_source',None) else None
            self._last_formal_source=source
            self._last_formal_asset=asset
            name=Path(getattr(self.repair,'loaded_source',asset.source_file)).name if getattr(self.repair,'loaded_source',asset.source_file) else ''
            if not name and self.repair.job_root:
                import json
                request=json.loads((self.repair.job_root/'request.json').read_text(encoding='utf-8'))
                name=Path(request['input_path']).name
            self.model_name.setText(name or '当前模型');self._asset_id=identity;self.last_feedback=''
            self.metric_summary.setText('当前版本尚无优化或独立评价结果。');self.metric_summary.setMinimumHeight(0)
            if not self.repair.pending_review:
                self.repair.review_summary.setText('当前正式版本；请生成新的处理预览。');self.repair.patch_summary.setText('当前版本尚无待接受补片。')
        if n.current_asset is None or n.current_asset.version_id!=asset.version:
            diagnosis=self.repair.accepted_diagnosis or self.repair.diagnosis
            roles=self.repair.boundary_roles.mapping(asset,diagnosis) if diagnosis and diagnosis.get('input_version')==asset.version else {}
            n.set_asset(to_optimization(asset,roles))
        if self.repair.pending_review is None:self._set_viewport(0 if self.current_step in ('repair','export') else 1)

    def refresh_state(self):
        r=self.repair;n=self.numerical;busy=r.process is not None or n.jobs.busy;pending=r.pending_review is not None;has=r.asset is not None
        for proxy,source in self._ribbon_actions:proxy.setEnabled(source.isEnabled())
        self.refresh_objects();self.apply_object_display()
        self.state_badge.setText('计算中' if busy else '预览待接受' if pending else '当前正式版本 '+r.asset.version[:8] if has else '尚未打开模型')
        self.stage_button.setVisible(self.current_step in ('optimize','evaluate') and not pending);self.stage_button.setEnabled(has and n.current_candidate is not None and not busy and not pending)
        if n.current_candidate and n.optimization_result:
            selected=next((item for item in n.optimization_result.get('attempts',[]) if item.get('version_id')==n.current_candidate.version_id),{})
            self.stage_button.setEnabled(bool(selected.get('screening_passed')) and not busy and not pending)
            self.stage_button.setText('预览所选优化方案' if selected.get('final_passed') else '复核并预览所选方案')
        for widget in (r.import_button,r.units):widget.setEnabled(not busy and not pending)
        for widget in (r.diagnose_button,r.export_button):widget.setEnabled(has and not busy and not pending)
        r.undo_button.setEnabled(has and bool(r.asset.parent_version) and not busy and not pending)
        self.redo_button.setEnabled(has and bool(r.redo_stack) and not busy and not pending)
        self.before_after_button.setEnabled(bool(getattr(self,'previous_asset',None)) and not busy and not pending)
        r.accept_button.setEnabled(pending and not busy);r.discard_button.setEnabled(pending and not busy);self.cancel_button.setEnabled(busy);r.task_progress.setVisible(busy)
        n.run_button.setEnabled(has and not busy and not pending);self.evaluate_button.setEnabled(has and not busy and not pending)
        # Keep scroll areas readable while protecting only mutable controls.
        self.settings.setEnabled(True)
        for widget in self.settings.findChildren(QComboBox)+self.settings.findChildren(QLineEdit)+self.settings.findChildren(QSpinBox)+self.settings.findChildren(QDoubleSpinBox)+self.settings.findChildren(QCheckBox):widget.setEnabled(not busy and not pending)
        for widget in (r.boundary_advice_button,r.confirm_advice_button):widget.setEnabled(has and not busy and not pending)
        self.observe_candidate_button.setEnabled(bool(n.current_candidate and n.optimization_result and has and n.optimization_result.get('input_version')==r.asset.version) and not busy and not pending)
        searching=n.search.isChecked() and n.operation.currentData()=='qem';self.search_explanation.setVisible(searching)
        if searching:
            for widget in (n.ratio,n.target_faces,n.target_mode):widget.setEnabled(False)
        key=(r.asset.version if has else None,n.limit_d95.value(),n.limit_max.value(),n.limit_area.value())
        if key!=getattr(self,'_limits_key',None):
            self._limits_key=key
            if has:
                import numpy as np
                diagonal=float(np.linalg.norm(np.ptp(r.asset.vertices,axis=0)))
                self.limits_explanation.setText(f'当前验收门槛：D95 ≤ {diagonal*n.limit_d95.value():.5g}；采样最大偏差 ≤ {diagonal*n.limit_max.value():.5g}（{r.asset.source_unit or "原坐标单位"}）；面积变化 ≤ {n.limit_area.value()*100:.3g}%。\n这些是允许的形状变化，不是处理强度。未通过也会显示候选，不能直接接受。')
        self.color_mode.setEnabled(self.viewport.currentIndex()==1)
        r.dual_view.setVisible(pending and self.viewport.currentIndex()==0);r.show_changes.setVisible(pending and self.viewport.currentIndex()==0)
        self.preview_legend.setText('误差色图：紫色偏差小、黄色偏差大；灰色面未采样。实体模式使用对象列表颜色。' if self.viewport.currentIndex()==1 else '修复变化：绿=新增、红=删除、橙=翻面；诊断：黄=边界、紫=退化/异常点。')
        self.status.setText(r.task_stage.text() if r.process else n.status_label.text() if n.jobs.busy else '预览未提交，请检查后接受或放弃' if pending else self.last_feedback or '就绪 · 仅导出当前正式版本')
        n.table.setVisible(bool(n.optimization_result and n.optimization_result.get('attempts')) and getattr(self,'current_result_operation',(n.last_result or {}).get('operation')) in ('optimize','verify_candidate'))
        r.review_banner.setText('预览未提交 · 当前版本保留' if pending else '处理流程：生成方案 → 预览 → 接受或放弃')

    def refresh_objects(self):
        r=self.repair;n=self.numerical;entries=[]
        def add(asset,label,state):
            if asset is not None and not any(version_of(e['asset'])==version_of(asset) for e in entries):entries.append(dict(asset=asset,label=label,state=state))
        add(r.asset,self.model_name.text(),'正式版本')
        if getattr(self,'previous_asset',None) is not None and not r.pending_review:add(self.previous_asset,'接受前模型（历史只读）','历史对照')
        if r.pending_review:add(r.pending_review.candidate,'修复 / 优化结果预览','待接受')
        elif self.viewport.currentIndex()==1 and n.viewer.last_comparison:
            reference,candidate,_=n.viewer.last_comparison
            operation=(n.last_result or {}).get('operation')
            if not r.asset or version_of(reference)==r.asset.version or operation in ('evaluate','convert'):
                add(reference,'输入参考','参考副本')
                operation_name=getattr(candidate,'operation','optimize');method={'qem':'简化','laplacian':'平滑','taubin':'Taubin平滑','remesh':'重划分'}.get(operation_name,'优化')
                add(candidate,'独立回读结果' if operation=='convert' else '对比模型' if operation=='evaluate' else str(method)+'结果预览','已回读' if operation=='convert' else '仅评价' if operation=='evaluate' else '候选预览')
        self.objects.bind(entries)
        labels=[]
        for entry in entries:
            style=self.objects.styles[version_of(entry['asset'])];labels.append((style['alias'] or entry['label'])+' ['+entry['state']+']'+('（已隐藏）' if not style['visible'] else ''))
        self.view_identity.setText('当前对象：'+' ｜ '.join(labels) if labels else '当前操作模型：尚未打开')

    def show_accepted_comparison(self):
        previous=getattr(self,'previous_asset',None)
        if previous is None or self.repair.asset is None:return
        self.numerical.viewer.show_comparison(to_optimization(previous),to_optimization(self.repair.asset))
        self.numerical.viewer.context.setText('左：接受前历史版本 · 右：当前正式版本（只读对照，不修改模型）')
        self._set_viewport(1);self.notify('正在对照接受前后模型，当前正式版本保持不变。')

    def _numerical_busy(self,busy):
        if busy:
            self.metric_summary.setText('当前任务正在计算，结果尚未生成。');self.metric_summary.setMinimumHeight(0)
            self.numerical.report_viewer.clear_report();self.numerical.table.hide()
            self.notify('任务已开始；正在计算与复检，请等待结果或点击取消。')

    def apply_object_display(self,force=False):
        if not hasattr(self,'objects'):return
        r=self.repair;n=self.numerical
        main=r.display_asset() if r.asset else None
        other=r.pending_review.input_asset if r.pending_review and r.preview_side.currentIndex()==0 else r.pending_review.candidate if r.pending_review else None
        targets=[(self.viewer.plotter,main,('base_mesh',*self.viewer.highlight_actors)),(self.viewer.other_plotter,other,('other_mesh',))]
        for index,renderer in enumerate(n.viewer.plotter.renderers):targets.append((renderer,n.viewer.assets.get(index),('reference_mesh' if index==0 else 'candidate_mesh','distance_cloud','highlight')))
        signature=tuple((id(renderer),version_of(asset) if asset else None,tuple((name,id(actor)) for name,actor in renderer.actors.items() if name in names),tuple(self.objects.styles.get(version_of(asset),{}).items()) if asset else ()) for renderer,asset,names in targets)
        if not force and signature==getattr(self,'_display_signature',None):return
        self._display_signature=signature
        for renderer,asset,names in targets:
            if asset is None:continue
            version=version_of(asset);style=self.objects.styles.get(version)
            if not style:continue
            for name,actor in renderer.actors.items():
                if name in names or name.startswith('change_'):
                    actor.SetVisibility(style['visible'])
                    if hasattr(actor,'prop'):
                        actor.prop.opacity=style['opacity']/100
                        if name in ('base_mesh','other_mesh') or (name in ('reference_mesh','candidate_mesh') and n.viewer.error_mode=='solid'):actor.prop.color=style['color']
        if self.viewport.currentIndex()==0:self.viewer.plotter.render();self.viewer.other_plotter.render()
        else:n.viewer.plotter.render()

    def notify(self,text,level='info',directory=None):
        colors={'info':('#edf3fa','#2d5c89'),'success':('#e8f4ec','#286647'),'warning':('#fff4dc','#8d641c'),'error':('#fcebea','#a13932')}
        background,color=colors.get(level,colors['info']);self.feedback.setText(text);self.feedback.setStyleSheet(f'padding:4px 7px;background:{background};color:{color};border:1px solid {color};')
        if directory:self.result_folder=Path(directory);self.folder_button.setEnabled(self.result_folder.is_dir())

    def _repair_finished(self,result):
        self.current_result_operation=getattr(self.repair,'active_operation','repair')
        if self.repair.job_root and result:
            try:
                from ..member2.reporting import render_report
                report=render_report({**result,'operation':getattr(self.repair,'active_operation','repair')},self.repair.job_root)
                self.numerical.report_viewer.load_report(report)
            except Exception as error:self.repair.log.appendPlainText('报告生成失败：'+str(error))
        status=result.get('status');errors=result.get('errors',[]);warnings=result.get('warnings',[])
        warnings=[explain_reasons([warning]) for warning in warnings]
        if 'suggestions' in result.get('metrics',{}):
            m=result['metrics'];self.repair.review_summary.setText(f"非流形建议搜索完成：复检 {m['examined']} 个候选，找到 {len(m['suggestions'])} 个通过方案。请在左侧下拉框选择，再查看方案位置和边界/分量变化。")
            self.repair.patch_summary.setText('预算限制每轮最多检查的候选数，不代表所有可能修复都已穷举。');self.show_results()
            self.notify(self.repair.suggestion_status.text(),'success' if m['suggestions'] else 'warning',self.repair.job_root);return
        if status!='completed':self.notify(('任务已取消，原模型保留。' if status=='cancelled' else '任务未完成，原模型保留：'+'；'.join(errors)),'warning' if status=='cancelled' else 'error',self.repair.job_root);return
        if self.repair.pending_review:self.notify('预览已生成：请对照前后模型和变化指标，接受后才更新正式版本。'+(' 提醒：'+'；'.join(warnings) if warnings else ''),'warning' if warnings else 'success',self.repair.job_root)
        else:self.notify('模型检查完成。'+(' 提醒：'+'；'.join(warnings) if warnings else ' 可在问题列表中点击定位。'),'warning' if warnings else 'success',self.repair.job_root)

    def _export_finished(self,result):
        warnings=result.get('warnings',[])
        if result['status']=='completed':self.notify('已导出当前正式版本：'+result['path']+(' · '+'；'.join(warnings) if warnings else ''),'warning' if warnings else 'success',Path(result['path']).parent)
        else:self.notify('导出失败：'+'；'.join(result.get('errors',[])),'error')

    def _review_resolved(self,event):
        import json
        directory=Path(event['directory'])
        try:
            from ..member2.reporting import render_report
            record=json.loads((directory/'result.json').read_text(encoding='utf-8'));record['user_review']=event['decision']
            record['operation']='repair';self.numerical.report_viewer.load_report(render_report(record,directory))
        except Exception as error:self.repair.log.appendPlainText('审核报告更新失败：'+str(error))

    def review_optimization(self):
        try:
            n=self.numerical;reference=self.repair.asset
            if reference is None or n.jobs.busy or self.repair.process is not None or self.repair.pending_review:raise ValueError('请先完成当前任务或处理待接受预览')
            if n.current_candidate is None or not n.optimization_result:raise ValueError('请先生成并选择优化方案')
            if n.optimization_result.get('input_version')!=reference.version:raise ValueError('参考版本已改变，请重新优化')
            item=next(x for x in n.optimization_result['attempts'] if x.get('version_id')==n.current_candidate.version_id)
            if not item.get('screening_passed'):raise ValueError('该方案未通过筛选，只能观察和查看原因；请调整处理目标后重算，不能直接接受。')
            if not item.get('final_passed'):
                directory=self.root/'runs'/('verify_'+uuid.uuid4().hex[:10]);directory.mkdir(parents=True);path=save_asset(n.current_asset,directory/'input.npz');self._review_requested=True
                n.jobs.submit({'operation':'verify_candidate','input_path':str(path),'output_dir':str(directory),'verification':n.optimization_result,'candidate_id':item['candidate_id'],'provider':n.diagnostic_provider});return
            candidate=from_optimization(n.current_candidate,reference);path=n.optimization_dir/'shared_review_candidate.npz';save_mesh(candidate,path)
            self.repair.start_job('review_optimization',parameters={'candidate_path':str(path.resolve()),'verification':n.optimization_result})
        except Exception as error:self.canvas_notice.setText('无法预览：'+str(error));n.log.appendPlainText(str(error))

    def _show_pending(self):
        if self.repair.pending_review:
            self.show_results()
            self._set_viewport(0);self.inspector.setCurrentIndex(0);self.canvas_notice.setText('预览尚未替换当前模型。绿色为新增面、红色为删除面；接受后继续下一步。')
            self.refresh_state()

    def _numerical_finished(self,result):
        self.current_result_operation=result.get('operation')
        self.show_results()
        requested=self._review_requested;self._review_requested=False;self.sync_reference();self._update_metric_summary(result)
        if result.get('operation') in ('evaluate','convert'):
            self.numerical.table.hide();self.repair.review_summary.setText('独立误差评价结果；不会修改正式版本。' if result.get('operation')=='evaluate' else '格式转换及独立回读结果。');self.repair.patch_summary.clear()
        if result.get('status')=='completed':
            if result.get('operation')=='convert':
                self.inspector.setCurrentIndex(2)
                if result.get('preview_assets'):self._set_viewport(1)
            else:self.inspector.setCurrentIndex(0);self._set_viewport(1)
        if requested and result.get('status')=='completed' and result.get('decision')=='accepted':QTimer.singleShot(0,self.review_optimization)
        elif requested:self.canvas_notice.setText('所选方案未通过最终复核；原模型保留，请查看原因。')
        self.last_feedback=('任务未完成：'+'；'.join(result.get('errors',[]))) if result.get('status') not in ('completed',) else '计算完成 · 当前模型尚未替换'
        if result.get('status')=='completed' and result.get('decision')=='rejected':
            self.last_feedback='没有方案通过阈值；可点选查看偏差，或调整高级参数。'
        reasons=result.get('reason_codes',[])+result.get('errors',[])
        if not reasons and result.get('decision')=='rejected':reasons=sorted({reason for item in result.get('attempts',[]) for reason in item.get('reason_codes',[])})
        message=('转换和独立回读完成，正式模型未改变。' if result.get('operation')=='convert' else '双向误差评价完成，正式模型未改变。' if result.get('operation')=='evaluate' else '优化计算完成；请选择方案检查并预览，接受后才更新正式版本。')
        if result.get('status')!='completed':message='任务未完成，正式版本保留。'
        elif result.get('decision')=='rejected':message='没有方案通过当前阈值，正式版本保留。'
        self.notify(message+(' 原因：'+explain_reasons(reasons) if reasons else ''),'error' if result.get('status') not in ('completed','cancelled') else 'warning' if reasons or result.get('status')=='cancelled' else 'success',result.get('output_dir'))
        for row,item in enumerate((self.numerical.optimization_result or {}).get('attempts',[])):
            if self.numerical.table.item(row,0):self.numerical.table.item(row,0).setText(str(row+1))
            if self.numerical.table.item(row,4):
                self.numerical.table.item(row,4).setText('可预览' if item.get('final_passed') and item['diagnosis']['status']=='passed' else '待复核' if item.get('screening_passed') else '未通过')
            if self.numerical.table.item(row,5):self.numerical.table.item(row,5).setText(explain_reasons(item.get('reason_codes',[])) or '结构与误差检查未记录拒绝原因')
            for column in range(self.numerical.table.columnCount()):
                cell=self.numerical.table.item(row,column)
                if cell:
                    cell.setToolTip('方案 '+item['candidate_id']+'\n'+explain_reasons(item.get('reason_codes',[]))+('\n最终独立复核通过' if item.get('final_passed') else '\n尚未通过最终复核；正式版本未改变'))
                    cell.setForeground(QBrush(QColor('#286647' if item.get('final_passed') else '#8d641c' if item.get('screening_passed') else '#a13932')))
        for column,width in ((0,42),(1,65),(2,85),(3,85),(4,85)):self.numerical.table.setColumnWidth(column,width)
        self.numerical.table.setColumnWidth(5,290)
        self.refresh_state()

    def show_results(self):
        self.results_toggle.setChecked(True)
        sizes=self.work_area.sizes()
        if len(sizes)>1 and sizes[1]<140:
            height=max(self.work_area.height(),400);self.work_area.setSizes([max(180,height-230),230])

    def _update_metric_summary(self,result=None):
        n=self.numerical;result=result or n.last_result or n.optimization_result or {};metrics=result.get('metrics',{})
        if result.get('attempts') and n.current_candidate:
            item=next((x for x in result['attempts'] if x.get('version_id')==n.current_candidate.version_id),{});metrics=item.get('final_metrics',item.get('metrics',{}))
        if metrics:
            text=f"双向平均偏差 ASD：{metrics.get('asd',0):.6g}\nD95：{metrics.get('d95',0):.6g}\n采样最大偏差：{metrics.get('sampled_max',0):.6g}\n距离单位：{metrics.get('coordinate_unit','原坐标单位')}\n面积变化：{100*metrics.get('area_change',0):.3g}%"
            if metrics.get('volume_change') is not None:text+=f"\n单闭合壳体体积变化：{100*metrics['volume_change']:.3g}%"
            if result.get('attempts') and n.current_asset and n.current_candidate and (n.optimization_result or {}).get('input_version')==n.current_asset.version_id:
                before,after=len(n.current_asset.faces),len(n.current_candidate.faces)
                text=f'处理前 → 结果\n顶点：{len(n.current_asset.vertices):,} → {len(n.current_candidate.vertices):,}\n三角面：{before:,} → {after:,}（保留 {100*after/before:.2f}%）\n'+text
                selected=next((x for x in (n.optimization_result or {}).get('attempts',[]) if x.get('version_id')==n.current_candidate.version_id),{})
                if selected.get('reason_codes'):text+='\n未通过原因：'+explain_reasons(selected['reason_codes'])
                text+='\n正式版本尚未改变；接受预览后才提交。'
            self.metric_summary.setText(text)
            self.metric_summary.setMinimumHeight(self.metric_summary.fontMetrics().lineSpacing()*(text.count('\n')+1)+10)
        self.canvas_notice.setText('误差色图按各面上的采样均值着色，灰色面未采样；统计使用原始双向样本。')

    def choose_evaluation_file(self):
        path,_=QFileDialog.getOpenFileName(self,'选择对比模型',str(self.root),'模型 (*.stl *.npz *.ply *.obj)')
        if path:self.evaluation_path.setText(path);self.evaluation_unit.setCurrentIndex(0)

    def clear_external_evaluation(self,*_):
        if not hasattr(self,'metric_summary') or self.numerical.jobs.busy:return
        self.current_result_operation='evaluate_pending';self.numerical.evaluation_result=None
        self.numerical.table.hide();self.numerical.report_viewer.clear_report()
        self.metric_summary.setText('对比文件已更换；请点击“计算双向误差”生成本次结果。');self.metric_summary.setMinimumHeight(0)
        self.repair.review_summary.setText('新对比尚未计算。');self.repair.patch_summary.clear()
        self.numerical.viewer.clear_models()
        if self.numerical.current_asset:self.numerical.viewer.show_mesh(self.numerical.current_asset)

    def evaluate_external(self):
        try:
            if self.repair.asset is None:raise ValueError('请先打开参考模型')
            candidate=load_mesh(self.evaluation_path.text());reference=self.repair.asset
            if self.evaluation_unit.currentIndex():
                unit=self.evaluation_unit.currentText();candidate=replace(candidate,unit_status='confirmed',source_unit=unit,unit_to_mm={'mm':1.,'cm':10.,'m':1000.}[unit])
            if candidate.unit_status!=reference.unit_status:raise ValueError('单位状态不同，请明确确认单位后评价')
            if candidate.unit_status=='confirmed':candidate=replace(candidate,vertices=candidate.vertices*(candidate.unit_to_mm/reference.unit_to_mm),source_unit=reference.source_unit,unit_to_mm=reference.unit_to_mm)
            directory=self.root/'runs'/('evaluate_'+uuid.uuid4().hex[:10]);directory.mkdir(parents=True)
            a=save_asset(to_optimization(reference),directory/'input_reference.npz');b=save_asset(to_optimization(candidate),directory/'input_candidate.npz')
            self.numerical.jobs.submit({'operation':'evaluate','input_path':str(a),'candidate_path':str(b),'samples':self.evaluation_samples.value(),'output_dir':str(directory)})
        except Exception as error:self.canvas_notice.setText('无法评价：'+str(error))

    def show_optimization_result(self):
        n=self.numerical
        if n.optimization_result and n.current_candidate:
            rows=n.table.selectionModel().selectedRows()
            if rows:n.select_candidate(rows[0].row(),0)
            n.last_result=n.optimization_result;self.current_result_operation=n.last_result.get('operation');self._set_viewport(1);self._update_metric_summary(n.optimization_result);self.show_results();self.inspector.setCurrentIndex(0)
            if n.optimization_dir and (n.optimization_dir/'report.html').exists():n.report_viewer.load_report(n.optimization_dir/'report.html')
        else:self.notify('当前没有可观察的优化候选，请先生成并选中方案。','info')

    def change_view(self,index):
        if self.viewport.currentIndex()==0:self.repair.change_view(index)
        else:
            plotter=self.numerical.viewer.plotter;[plotter.view_isometric,plotter.view_xy,plotter.view_yz,plotter.view_xz][index]();plotter.render()

    def fit_view(self):
        if self.viewport.currentIndex()==0:self.repair.show_overview()
        else:
            plotter=self.numerical.viewer.plotter;plotter.reset_camera();plotter.camera.zoom(.85);plotter.render()

    def change_opacity(self,value):
        for entry in self.objects.entries:self.objects.styles[version_of(entry['asset'])]['opacity']=value
        self.objects._select()
        self.repair.change_opacity(value)
        for renderer in self.numerical.viewer.plotter.renderers:
            for name,actor in renderer.actors.items():
                if name in ('reference_mesh','candidate_mesh'):actor.prop.opacity=value/100
        self.numerical.viewer.plotter.render()

    def change_wire(self,checked):
        self.repair.render();self.numerical.viewer.wireframe=checked;self.numerical.viewer.redraw()

    def save_snapshot(self):
        if self.viewport.currentIndex()==0:self.repair.save_snapshot()
        else:
            path,_=QFileDialog.getSaveFileName(self,'保存当前对比视图','model_view.png','PNG (*.png)')
            if path:self.numerical.viewer.grab().save(path)

    def cancel_current(self):
        if self.numerical.jobs.busy:self.numerical.jobs.cancel()
        elif self.repair.process:self.repair.cancel()

    def closeEvent(self,event):
        if self.repair.process is not None or self.numerical.jobs.busy:self.cancel_current();event.ignore();return
        self.refresh_timer.stop();self.viewer.other_plotter.close();self.viewer.plotter.close();self.numerical.viewer.close_viewer();super().closeEvent(event)


def main():
    configure_application_identity()
    app=QApplication.instance() or QApplication(sys.argv);app.setApplicationName('医学三维工作台');app.setWindowIcon(project_icon());app.setStyle('Fusion');window=Workbench();window.show();return app.exec()
