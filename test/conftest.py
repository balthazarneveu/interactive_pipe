"""Suite-wide test isolation and crash diagnostics (helpers in ``isolation.py``).

- After a test that replaced the thread's asyncio loop (every gradio GUI
  build does), the replaced loops are collected right away, warnings
  silenced, instead of warning later inside an unrelated test.
- Qt windows a test leaves on screen are closed after it and Qt's deferred
  deletions run (``INTERACTIVE_PIPE_TEST_KEEP_WINDOWS=1`` keeps them, to
  check that the library alone copes with windows left behind).
- A native crash (``Fatal Python error``, dumped on stderr by pytest's
  faulthandler plugin with every thread's Python frames) names its test: the
  running test id is kept in ``.pytest_cache/interactive_pipe_running_test.txt``
  (``INTERACTIVE_PIPE_TEST_BREADCRUMB`` to move it). A test still running
  after ``INTERACTIVE_PIPE_TEST_HANG_DUMP`` seconds (default 300, 0 disables)
  appends every thread's stack to that file and keeps running.
"""

import faulthandler
import os
from pathlib import Path

import pytest
from isolation import CrashBreadcrumb, EventLoopSweeper, close_qt_windows

_sweeper = EventLoopSweeper()
_breadcrumb = None
_hang_dump_seconds = 0.0


def pytest_configure(config):
    global _breadcrumb, _hang_dump_seconds
    path = os.environ.get("INTERACTIVE_PIPE_TEST_BREADCRUMB")
    target = Path(path) if path else Path(config.rootpath) / ".pytest_cache" / "interactive_pipe_running_test.txt"
    try:
        _breadcrumb = CrashBreadcrumb(target)
    except OSError:  # read-only checkout: diagnostics only, never fail the run
        _breadcrumb = None
    try:
        _hang_dump_seconds = float(os.environ.get("INTERACTIVE_PIPE_TEST_HANG_DUMP", "300"))
    except ValueError:
        _hang_dump_seconds = 300.0


def pytest_unconfigure(config):
    global _breadcrumb
    if _breadcrumb is not None:
        faulthandler.cancel_dump_traceback_later()
        _breadcrumb.finished()
        _breadcrumb = None


def pytest_report_header(config):
    if _breadcrumb is not None:
        return f"running test breadcrumb (for native crashes): {_breadcrumb.path}"
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    if _breadcrumb is not None:
        _breadcrumb.running(item.nodeid)
        if _hang_dump_seconds > 0:
            faulthandler.dump_traceback_later(_hang_dump_seconds, repeat=False, file=_breadcrumb.fd)
    _sweeper.before_test()
    try:
        yield
    finally:
        if not os.environ.get("INTERACTIVE_PIPE_TEST_KEEP_WINDOWS"):
            close_qt_windows()
        _sweeper.after_test()
        if _breadcrumb is not None and _hang_dump_seconds > 0:
            faulthandler.cancel_dump_traceback_later()
