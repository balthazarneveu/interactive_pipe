"""Qt binding detection shared by all Qt-based GUI modules.

Runs the PyQt6 -> PyQt5 (-> PySide6) import cascade exactly once and
re-exports every Qt symbol plus the optional matplotlib-qtagg widgets.
IMPORTANT: this module must keep raising ModuleNotFoundError("No PyQt") at
import time when no Qt binding is installed - helper/choose_backend.py
catches that error to fall back to the matplotlib backend, and the smoke
tests rely on it via pytest.importorskip.

Static typing: the type checker only sees the PyQt6 declarations in the
TYPE_CHECKING branch; the runtime cascade lives in the else-branch so the
unresolved PyQt5/PySide6 fallback imports cannot poison the exported symbol
types (pyright would otherwise refuse to re-export them).
"""

import logging
from typing import TYPE_CHECKING

__all__ = [
    "MPL_SUPPORT",
    "PYQTVERSION",
    "Curve",
    "Figure",
    "FigureCanvas",
    "QApplication",
    "QAudioOutput",
    "QFrame",
    "QGridLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QImage",
    "QLabel",
    "QMediaContent",
    "QMediaPlayer",
    "QMessageBox",
    "QPixmap",
    "QPushButton",
    "Qt",
    "QtFrameBase",
    "QTimer",
    "QtWidgetBase",
    "QUrl",
    "QVBoxLayout",
    "QWidget",
    "SingleCurve",
    "Table",
]

if TYPE_CHECKING:
    from typing import Any, Optional

    # the runtime alias FigureCanvas is not in the matplotlib stubs
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from PyQt6.QtCore import Qt, QTimer, QUrl
    from PyQt6.QtGui import QImage, QPixmap
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtWidgets import (
        QApplication,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from interactive_pipe.data_objects.curves import Curve, SingleCurve
    from interactive_pipe.data_objects.table import Table

    PYQTVERSION: Optional[int]
    MPL_SUPPORT: bool
    QMediaContent: Any  # only exists under PyQt5
    QtWidgetBase = QWidget
    QtFrameBase = QFrame
else:
    PYQTVERSION = None
    MPL_SUPPORT = False
    # Only the PyQt5 branch imports QMediaContent; default it so
    # `from qt_backend import QMediaContent` works under PyQt6 too.
    QMediaContent = None

    if not PYQTVERSION:
        try:
            from PyQt6.QtCore import Qt, QTimer, QUrl
            from PyQt6.QtGui import QImage, QPixmap
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtWidgets import (  # noqa: F811
                QApplication,
                QFrame,
                QGridLayout,
                QGroupBox,
                QHBoxLayout,
                QLabel,
                QMessageBox,
                QPushButton,
                QVBoxLayout,
                QWidget,
            )

            PYQTVERSION = 6
        except ImportError:
            logging.warning("Cannot import PyQt 6")
            try:
                from PyQt5.QtCore import Qt, QTimer, QUrl
                from PyQt5.QtGui import QImage, QPixmap
                from PyQt5.QtMultimedia import QAudioOutput, QMediaContent, QMediaPlayer
                from PyQt5.QtWidgets import (  # noqa: F811
                    QApplication,
                    QFrame,
                    QGridLayout,
                    QGroupBox,
                    QHBoxLayout,
                    QLabel,
                    QMessageBox,
                    QPushButton,
                    QVBoxLayout,
                    QWidget,
                )

                PYQTVERSION = 5
                logging.warning("Using PyQt 5")
            except ImportError:
                raise ModuleNotFoundError("No PyQt")

    # NOTE: unreachable today - the PyQt5 except-branch above raises before this
    # block can run, so a PySide6-only machine never reaches it (tech-debt
    # backlog, behavior decision pending). Moved verbatim from qt_gui.py.
    if not PYQTVERSION:
        try:
            from PySide6.QtCore import Qt, QTimer, QUrl  # noqa: F811
            from PySide6.QtGui import QImage, QPixmap  # noqa: F811
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: F811
            from PySide6.QtWidgets import (  # noqa: F811
                QApplication,
                QFrame,
                QGridLayout,
                QGroupBox,
                QHBoxLayout,
                QLabel,
                QMessageBox,
                QPushButton,
                QVBoxLayout,
                QWidget,
            )

            PYQTVERSION = 6
        except ImportError:
            logging.warning("Cannot import PySide 6")

    if not PYQTVERSION:
        logging.warning("Cannot import PyQt or PySide - disable backend")
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvas  # type: ignore[reportAttributeAccessIssue]
        from matplotlib.figure import Figure

        from interactive_pipe.data_objects.curves import Curve, SingleCurve
        from interactive_pipe.data_objects.table import Table

        MPL_SUPPORT = True
    except ImportError:
        FigureCanvas = None
        Figure = None
        Curve = None
        SingleCurve = None
        Table = None
        logging.warning("No support for Matplotlib widgets for Qt")

    # Conditional base classes for widgets ("QWidget if PYQTVERSION else object")
    QtWidgetBase = QWidget if PYQTVERSION else object
    QtFrameBase = QFrame if PYQTVERSION else object
