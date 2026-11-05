import os
os.environ.setdefault("QT_API", "pyside6")

from pathlib import Path
import argparse
import sys
from medical_mesh.ui.bootstrap import configure_qt
configure_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from medical_mesh.ui.main_window import MainWindow


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--smoke-test", help="save an initial window screenshot, then exit")
    parser.add_argument("--patella-demo", action="store_true", help="open the real MRI course demonstration page")
    args = parser.parse_args(argv)
    configure_qt()  # Recheck immediately before Qt enumerates platform plug-ins.
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    window = MainWindow(args.project_dir, off_screen=bool(args.smoke_test))
    window.show()
    if args.patella_demo:
        window.tabs.setCurrentWidget(window.demo)
        window.workspace.setCurrentWidget(window.demo_overview)
    else:
        window.load_demo()
    if args.smoke_test:
        def capture():
            path = Path(args.smoke_test).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(path))
            window.close()
            app.quit()
        QTimer.singleShot(1500, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
