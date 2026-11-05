"""Unified manual workflow: accepted mesh -> optimization -> shared human review."""
import sys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QMainWindow,QTabWidget,QPushButton,QLabel,QVBoxLayout,QWidget
from ..integration.member2 import to_optimization,from_optimization
from ..member2.core.model import load_asset
from ..io.mesh_io import save_mesh
from ..member2.ui.main_window import MainWindow as NumericalWorkbench
from .member1_panel import Member1Panel
from .preview_host import ViewerAdapter


class Workbench(QMainWindow):
    def __init__(self,root=None,session_root=None,off_screen=False):
        super().__init__();self.root=Path(root or Path(__file__).resolve().parents[3])
        self.setWindowTitle('医学三维模型工作台 · 诊断修复 / 优化评价 / CAD转换')
        self.resize(1500,1000);self.pages=QTabWidget();self.setCentralWidget(self.pages)
        self.viewer=ViewerAdapter(self)
        self.repair=Member1Panel(self.viewer,session_root or self.root/'results/gui_session')
        self.pages.addTab(self.repair,'1 · 导入、诊断与修复')
        self.numerical=NumericalWorkbench(self.root,off_screen=off_screen)
        self.numerical.setWindowFlags(Qt.Widget)
        self.numerical.open_button.clicked.disconnect()
        self.numerical.open_button.setText('到导入与修复页选择模型')
        self.numerical.open_button.clicked.connect(lambda:self.pages.setCurrentWidget(self.repair))
        self.numerical.units.hide();self.numerical.unit_label.hide()
        self.numerical.open_file=lambda:self.pages.setCurrentWidget(self.repair)
        self.numerical.diagnostic_provider='medical_mesh.integration.member2:diagnose_pair'
        self.stage_button=QPushButton('将所选优化候选送入统一预览审核')
        self.stage_button.clicked.connect(self.review_optimization)
        self.numerical.centralWidget().layout().insertWidget(2,self.stage_button)
        self.pages.addTab(self.numerical,'2 · 优化、评价与CAD转换')
        self.repair.asset_changed.connect(self.sync_reference)
        self.repair.diagnosis_changed.connect(lambda _:self.sync_reference())
        self.numerical.jobs.busy_changed.connect(lambda busy:QTimer.singleShot(0,self.sync_reference) if not busy else None)
        self.stage_button.setEnabled(False)

    def sync_reference(self,*_):
        asset=self.repair.asset
        if asset is None:return
        if self.numerical.jobs.busy:return
        if self.numerical.current_asset is None or self.numerical.current_asset.version_id!=asset.version:
            diagnosis=self.repair.accepted_diagnosis or self.repair.diagnosis
            roles=self.repair.boundary_roles.mapping(asset,diagnosis) if diagnosis and diagnosis.get('input_version')==asset.version else {}
            self.numerical.set_asset(to_optimization(asset,roles))
        self.stage_button.setEnabled(self.repair.process is None and self.repair.pending_review is None)

    def review_optimization(self):
        try:
            panel=self.numerical;reference=self.repair.asset
            if reference is None or panel.jobs.busy or self.repair.process is not None or self.repair.pending_review:
                raise ValueError('请先完成当前任务或处理待接受预览')
            if panel.current_candidate is None or not panel.optimization_result:raise ValueError('请先生成并选择优化候选')
            if panel.optimization_result.get('input_version')!=reference.version:raise ValueError('参考版本已改变，请重新优化')
            candidate=from_optimization(panel.current_candidate,reference)
            directory=panel.optimization_dir;path=directory/'shared_review_candidate.npz';save_mesh(candidate,path)
            self.repair.start_job('review_optimization',parameters={'candidate_path':str(path.resolve()),
                'verification':panel.optimization_result})
            self.pages.setCurrentWidget(self.repair)
        except Exception as error:self.numerical.log.appendPlainText('不能提交审核：'+str(error))

    def closeEvent(self,event):
        if self.repair.process is not None or self.numerical.jobs.busy:
            if self.repair.process:self.repair.cancel()
            if self.numerical.jobs.busy:self.numerical.jobs.cancel()
            self.statusBar().showMessage('正在取消后台任务，结束后请再次关闭。');event.ignore();return
        self.viewer.other_plotter.close();self.viewer.plotter.close();self.numerical.viewer.close_viewer()
        super().closeEvent(event)


def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion');window=Workbench();window.show()
    return app.exec()
