"""Select this environment's Qt plug-ins without changing system Qt settings."""
import importlib.util
import os
from pathlib import Path
import stat
import sys


def configure_qt():
    os.environ["QT_API"] = "pyside6"
    spec = importlib.util.find_spec("PySide6")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("PySide6-Essentials is not installed in this environment")
    plugins = Path(next(iter(spec.submodule_search_locations))) / "Qt/plugins"
    platforms = plugins / "platforms"
    if sys.platform == "darwin":
        # Qt skips Finder-hidden plug-ins during enumeration. Restored local
        # environments can carry UF_HIDDEN; fix only our installed platform files.
        for path in platforms.glob("*.dylib"):
            flags = path.stat().st_flags
            if flags & stat.UF_HIDDEN:
                os.chflags(path, flags & ~stat.UF_HIDDEN)
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)
