"""Project branding backed by the user's original logo asset."""
import sys
from pathlib import Path
from PySide6.QtGui import QIcon

LOGO_PATH=Path(__file__).with_name('assets')/'project_logo.png'


def project_icon():
    return QIcon(str(LOGO_PATH))


def configure_application_identity():
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MedicalMesh.Workbench')
