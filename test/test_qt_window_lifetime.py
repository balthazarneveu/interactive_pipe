"""A Qt window dropped while still on screen is deleted by Qt's event loop,
never by the garbage collector in the middle of one of its own paint events.

The native crash of the full test suite (``Fatal Python error: Segmentation
fault`` in ``FigureCanvasQTAgg.paintEvent`` -> ``QPainter.eraseRect``): a test
left a window with a matplotlib canvas on screen, the next test's event
processing painted it, and the Python code of that paint event triggered a
garbage collection that deleted the unreachable window, canvas included
(``QPaintDevice: Cannot destroy paint device that is being painted``).
"""

import gc
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.graphical.qt_backend import QApplication, QLabel, QWidget  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"

DROPPED_WINDOW_SCRIPT = textwrap.dedent(
    """
    import gc
    import numpy as np
    from matplotlib.backends import backend_qtagg
    from interactive_pipe import interactive
    from interactive_pipe.data_objects.curves import Curve, SingleCurve
    from interactive_pipe.data_objects.table import Table
    from interactive_pipe.graphical.qt_backend import QApplication
    from interactive_pipe.graphical.qt_gui import InteractivePipeQT
    from interactive_pipe.headless.pipeline import HeadlessPipeline

    @interactive()
    def brighten(img, gain=(0.5, [0.0, 1.0])):
        return img * gain

    @interactive()
    def make_curve(img):
        return Curve([SingleCurve(y=img.mean(axis=0))], ylabel="mean")

    @interactive()
    def make_table(img):
        return Table(img[:2, :2], columns=["a", "b"])

    def mixed_pipeline(img):
        gray = brighten(img)
        curve = make_curve(img)
        tab = make_table(img)
        return [[gray, curve], [tab, gray]]

    def build_window(pipeline_function):
        pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
        gui = InteractivePipeQT(pipeline=pipeline, size=(300, 200))
        gui.pipeline.inputs = [np.linspace(0, 1, 64).reshape(8, 8)]
        window = gui.window
        window.refresh()
        window.layout().activate()
        QApplication.processEvents()
        return window

    def first_test():  # leaves its window on screen, referenced by nothing but its own cycles
        window = build_window(mixed_pipeline)
        window.zoom_in()
        window.refresh()

    first_test()

    # what happened by chance in the test suite, made certain: a garbage
    # collection while a matplotlib canvas of that window is being painted
    paint = backend_qtagg.FigureCanvasQTAgg.copy_from_bbox
    def copy_from_bbox(canvas, bbox):
        gc.collect()
        return paint(canvas, bbox)
    backend_qtagg.FigureCanvasQTAgg.copy_from_bbox = copy_from_bbox

    second = build_window(mixed_pipeline)  # the next test: its event processing paints both windows
    print("survived")
    """
)


def test_collecting_a_shown_window_during_its_own_paint_does_not_crash(tmp_path):
    # in a fresh interpreter: before the fix this was a segmentation fault
    script = tmp_path / "dropped_window.py"  # the pipeline source must be in a file
    script.write_text(DROPPED_WINDOW_SCRIPT)
    env = dict(os.environ, PYTHONPATH=str(SRC), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    done = subprocess.run(
        [sys.executable, "-X", "faulthandler", str(script)], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr
    assert "survived" in done.stdout
    assert "Cannot destroy paint device" not in done.stderr


@interactive(lifetime_scale=(1.0, [0.0, 2.0]))
def lifetime_scale_filter(img, lifetime_scale=1.0):
    return img * lifetime_scale


def lifetime_window_pipeline(img):
    out = lifetime_scale_filter(img)
    return out


DROPPED_TITLE = "dropped window (lifetime test)"


def _drop_a_shown_window() -> None:
    pipeline = HeadlessPipeline.from_function(lifetime_window_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name=DROPPED_TITLE, size=(200, 100))
    gui.pipeline.inputs = [np.ones((4, 4))]
    gui.window.refresh()
    gui.window.show()


def _dropped_window_on_screen() -> bool:
    return any(widget.windowTitle() == DROPPED_TITLE for widget in QApplication.topLevelWidgets())


def test_a_collected_window_is_deleted_by_the_event_loop_not_by_the_collector():
    _drop_a_shown_window()
    gc.collect()
    assert _dropped_window_on_screen()  # handed to Qt, not deleted inside the collection
    core = sys.modules[QApplication.__module__.replace("QtWidgets", "QtCore")]  # the binding in use
    core.QCoreApplication.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)
    assert not _dropped_window_on_screen()


def test_defer_deletion_leaves_children_and_deleted_widgets_alone():
    _app = QApplication.instance() or QApplication([])
    sip = qt_gui._sip_module()
    if sip is None:
        pytest.skip("ownership is only handed over with PyQt (sip)")
    parent = QWidget()
    child = QLabel("child", parent)  # owned by its parent (C++)
    assert qt_gui.defer_deletion(child) is False
    sip.delete(child)
    assert qt_gui.defer_deletion(child) is False  # already deleted
    assert qt_gui.defer_deletion(parent) is True
    assert not sip.ispyowned(parent)
    del parent
    gc.collect()
