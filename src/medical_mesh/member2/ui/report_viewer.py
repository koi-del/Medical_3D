"""Read local HTML and JSON reports inside the desktop window."""
from pathlib import Path
import json
from PySide6.QtCore import QUrl, QByteArray, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTabWidget, QTextBrowser, QPlainTextEdit,QHBoxLayout,QPushButton,QDialog


class LocalReportBrowser(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.report_root = None
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def loadResource(self, kind, url):
        resolved = self.source().resolved(url)
        if not self.report_root or not resolved.isLocalFile():
            return QByteArray()
        path = Path(resolved.toLocalFile()).resolve()
        if not path.is_relative_to(self.report_root):
            return QByteArray()
        return super().loadResource(kind, resolved)


class ReportViewer(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.path_label = QLabel("尚无任务报告"); self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        toolbar=QHBoxLayout();toolbar.addWidget(self.path_label,1)
        self.fullscreen_button=QPushButton('全屏阅读报告');self.fullscreen_button.clicked.connect(self.show_fullscreen);toolbar.addWidget(self.fullscreen_button);layout.addLayout(toolbar)
        self.tabs = QTabWidget()
        self.browser = LocalReportBrowser()
        self.raw = QPlainTextEdit(); self.raw.setReadOnly(True)
        self.tabs.addTab(self.browser, "处理与质量报告");self.raw.hide()
        layout.addWidget(self.tabs)
        self.current_path=None

    def clear_report(self):
        if hasattr(self,'_full_window'):self._full_window.close()
        self.path_label.setText("本次报告尚未生成")
        self.browser.clear(); self.raw.clear()
        self.current_path=None

    def load_report(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        if (path.parent/'result.json').exists() and '完整记录</h2>' in path.read_text(encoding='utf-8'):
            from medical_mesh.member2.reporting import render_report
            render_report(json.loads((path.parent/'result.json').read_text(encoding='utf-8')),path.parent)
        self.current_path=path
        self.path_label.setText('本次处理报告 · '+path.parent.name);self.path_label.setToolTip(str(path))
        self.browser.report_root = path.parent
        self.browser.setSource(QUrl.fromLocalFile(str(path)))
        self.browser.reload()
        result = path.parent/"result.json"
        self.raw.setPlainText(json.dumps(json.loads(result.read_text(encoding="utf-8")), ensure_ascii=False, indent=2) if result.exists() else "此报告无同目录result.json。")

    def show_fullscreen(self):
        if not self.current_path:return
        dialog=QDialog(self);dialog.setWindowTitle('医学三维模型 · 完整质量报告');layout=QVBoxLayout(dialog)
        tools=QHBoxLayout();tools.addWidget(QLabel('报告全文 · 可滚动阅读和调整字号'),1)
        browser=LocalReportBrowser();browser.report_root=self.current_path.parent;browser.setSource(QUrl.fromLocalFile(str(self.current_path)))
        for label,action in [('字号＋',lambda:browser.zoomIn()),('字号－',lambda:browser.zoomOut()),('退出全屏',dialog.close)]:
            button=QPushButton(label);button.clicked.connect(action);tools.addWidget(button)
        layout.addLayout(tools);layout.addWidget(browser);self._full_window=dialog;dialog.showMaximized()
