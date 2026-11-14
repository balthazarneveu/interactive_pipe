"""The suite's isolation helpers (test/isolation.py, used by conftest.py)."""

import asyncio
import faulthandler
import gc
import time
import warnings

import pytest
from isolation import CrashBreadcrumb, EventLoopSweeper, close_qt_windows, current_event_loop


def _unclosed_loop_warnings(caught):
    return [w for w in caught if "unclosed event loop" in str(w.message)]


@pytest.fixture
def restore_event_loop():
    before = current_event_loop()
    yield
    loop = current_event_loop()
    asyncio.set_event_loop(before)
    if loop is not None and loop is not before:
        loop.close()


def _replace_the_loop_twice():
    # what gradio.utils.safe_get_lock does at every gr.Blocks() build
    for _ in range(2):
        asyncio.set_event_loop(asyncio.new_event_loop())


def test_replaced_loops_warn_whenever_they_are_collected(restore_event_loop):
    # the mechanism behind the order-dependent `check` failures
    _replace_the_loop_twice()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        gc.collect()
    assert _unclosed_loop_warnings(caught)


def test_the_sweeper_collects_replaced_loops_silently(restore_event_loop):
    sweeper = EventLoopSweeper()
    sweeper.before_test()
    _replace_the_loop_twice()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert sweeper.after_test()
        gc.collect()  # a later test's collection: nothing left to warn about
    assert _unclosed_loop_warnings(caught) == []


def test_the_sweeper_does_nothing_when_the_loop_did_not_change(restore_event_loop):
    sweeper = EventLoopSweeper()
    sweeper.before_test()
    assert sweeper.after_test() is False


def test_a_gradio_build_replaces_the_event_loop(restore_event_loop):
    gradio_utils = pytest.importorskip("gradio.utils")
    before = current_event_loop()
    gradio_utils.safe_get_lock()
    assert current_event_loop() is not before


def test_breadcrumb_names_the_running_test_and_takes_hang_dumps(tmp_path):
    breadcrumb = CrashBreadcrumb(tmp_path / "sub" / "running.txt")
    breadcrumb.running("test/test_a.py::test_long_name_first")
    breadcrumb.running("test/test_b.py::test_x")
    assert breadcrumb.path.read_text() == "running: test/test_b.py::test_x\n"
    faulthandler.dump_traceback_later(0.05, repeat=False, file=breadcrumb.fd)
    try:
        time.sleep(0.5)
    finally:
        faulthandler.cancel_dump_traceback_later()
    text = breadcrumb.path.read_text()
    assert text.startswith("running: test/test_b.py::test_x\n")
    assert "most recent call first" in text and "test_isolation.py" in text
    breadcrumb.finished()
    assert breadcrumb.path.read_text() == "running: (session finished)\n"


def test_close_qt_windows_closes_what_a_test_left_on_screen_and_runs_deferred_deletions():
    widgets = pytest.importorskip("PyQt6.QtWidgets")

    _app = widgets.QApplication.instance() or widgets.QApplication([])
    left_open = widgets.QWidget()
    left_open.setWindowTitle("left open by a test")
    left_open.show()
    deleted = []
    doomed = widgets.QWidget()
    doomed.destroyed.connect(lambda *_args: deleted.append(True))
    doomed.deleteLater()
    assert close_qt_windows() >= 1
    assert not left_open.isVisible()
    assert deleted == [True]
