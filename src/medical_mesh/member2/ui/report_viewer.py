"""Read local HTML and JSON reports inside the desktop window."""
from pathlib import Path
import json
from PySide6.QtCore import QUrl, QByteArray, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTabWidget, QTextBrowser, QPlainTextEdit


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
        layout.addWidget(self.path_label)
        self.tabs = QTabWidget()
        self.browser = LocalReportBrowser()
        self.raw = QPlainTextEdit(); self.raw.setReadOnly(True)
        self.tabs.addTab(self.browser, "HTML报告"); self.tabs.addTab(self.raw, "完整JSON")
        layout.addWidget(self.tabs)

    def clear_report(self):
        self.path_label.setText("本次报告尚未生成")
        self.browser.clear(); self.raw.clear()

    def load_report(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        self.path_label.setText(str(path))
        self.browser.report_root = path.parent
        self.browser.setSource(QUrl.fromLocalFile(str(path)))
        self.browser.reload()
        result = path.parent/"result.json"
        self.raw.setPlainText(json.dumps(json.loads(result.read_text(encoding="utf-8")), ensure_ascii=False, indent=2) if result.exists() else "此报告无同目录result.json。")
