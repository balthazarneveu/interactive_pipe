"""Qt binding import cascade (qt_backend.py).

The cascade runs once at import time, so each scenario runs in a subprocess
with an import hook that blocks selected bindings:
- no binding at all -> ModuleNotFoundError("No PyQt") (choose_backend and the
  smoke tests depend on this exact behavior)
- PySide6 only -> the backend loads with PYQTVERSION == 6 (Qt6 API)
"""

import subprocess
import sys

BLOCKER_PREAMBLE = """
import sys
import types

BLOCKED_TOPLEVEL = {blocked!r}

class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED_TOPLEVEL:
            raise ImportError("blocked: " + name)
        if name == "matplotlib.backends.backend_qtagg":
            # keep matplotlib from probing real Qt bindings in this scenario
            raise ImportError("blocked: " + name)
        return None

sys.meta_path.insert(0, _Blocker())
"""

NO_BINDING_SCRIPT = (
    BLOCKER_PREAMBLE.format(blocked=("PyQt6", "PyQt5", "PySide6"))
    + """
try:
    import interactive_pipe.graphical.qt_backend  # noqa: F401
except ModuleNotFoundError as exc:
    print("RAISED:" + str(exc))
else:
    print("NO_RAISE")
"""
)

PYSIDE6_ONLY_SCRIPT = (
    BLOCKER_PREAMBLE.format(blocked=("PyQt6", "PyQt5"))
    + """
def fake_module(name, attr_names):
    mod = types.ModuleType(name)
    for attr in attr_names:
        setattr(mod, attr, type(attr, (), {}))
    sys.modules[name] = mod
    return mod

pyside6 = fake_module("PySide6", [])
pyside6.QtCore = fake_module("PySide6.QtCore", ["QSize", "Qt", "QThread", "QTimer", "QUrl", "Signal"])
pyside6.QtGui = fake_module("PySide6.QtGui", ["QIcon", "QImage", "QPixmap"])
pyside6.QtMultimedia = fake_module("PySide6.QtMultimedia", ["QAudioOutput", "QMediaPlayer"])
pyside6.QtWidgets = fake_module(
    "PySide6.QtWidgets",
    [
        "QApplication",
        "QCheckBox",
        "QComboBox",
        "QDial",
        "QDoubleSpinBox",
        "QFileDialog",
        "QFrame",
        "QGridLayout",
        "QGroupBox",
        "QHBoxLayout",
        "QLabel",
        "QLineEdit",
        "QMenuBar",
        "QMessageBox",
        "QPushButton",
        "QSlider",
        "QSpinBox",
        "QVBoxLayout",
        "QWidget",
    ],
)

from interactive_pipe.graphical import qt_backend

print("PYQTVERSION:" + str(qt_backend.PYQTVERSION))
print("QAPP_IS_PYSIDE:" + str(qt_backend.QApplication is sys.modules["PySide6.QtWidgets"].QApplication))
print("WIDGET_BASE_IS_PYSIDE:" + str(qt_backend.QtWidgetBase is sys.modules["PySide6.QtWidgets"].QWidget))
"""
)


def run_script(script: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_no_qt_binding_raises_module_not_found():
    stdout = run_script(NO_BINDING_SCRIPT)
    assert "RAISED:No PyQt" in stdout


def test_pyside6_only_machine_uses_pyside6():
    stdout = run_script(PYSIDE6_ONLY_SCRIPT)
    assert "PYQTVERSION:6" in stdout
    assert "QAPP_IS_PYSIDE:True" in stdout
    assert "WIDGET_BASE_IS_PYSIDE:True" in stdout


NO_BINDING_CONTROL_SCRIPT = (
    BLOCKER_PREAMBLE.format(blocked=("PyQt6", "PyQt5", "PySide6"))
    + """
from interactive_pipe.graphical import qt_control
from interactive_pipe.headless.control import Control

print("AVAILABLE:" + str(qt_control.PYQT_AVAILABLE))
try:
    qt_control.ControlFactory.create_control(Control(0.5, [0.0, 1.0]), lambda *_: None)
except ModuleNotFoundError as exc:
    print("RAISED:" + str(exc))
"""
)


def test_qt_control_imports_without_binding_and_fails_loudly_on_use():
    stdout = run_script(NO_BINDING_CONTROL_SCRIPT)
    assert "AVAILABLE:False" in stdout
    assert "RAISED:PyQt is required for Qt controls" in stdout
