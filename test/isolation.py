"""Test-suite isolation helpers used by ``conftest.py`` (tested in test_isolation.py).

- ``EventLoopSweeper``: gradio's ``gr.Blocks()`` calls ``asyncio.set_event_loop``
  with a new loop several times per build, never closing the one it replaces.
  Those loops are garbage collected whenever the collector happens to run,
  with a ``ResourceWarning: unclosed event loop``; inside a later test that
  records warnings (``interactive-pipe check`` runs, ``pytest.warns``) the
  stray warning makes it fail depending on the test order. The sweeper
  collects them, warnings silenced, right after the test that replaced the loop.
- ``close_qt_windows``: windows a test leaves on screen are closed and the
  deletions Qt deferred (``deleteLater``, e.g. windows the garbage collector
  handed back to Qt, see ``qt_gui.defer_deletion``) are carried out between
  tests, outside any event handler: a window left behind would otherwise
  keep being painted by the next tests' event processing.
- ``CrashBreadcrumb``: the name of the running test in a small file, so a
  native crash (``Fatal Python error``, the faulthandler dump on stderr) can be
  tied to a test even with ``-q`` output or when the dump shows another thread.
"""

import asyncio
import gc
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Optional


def current_event_loop() -> Optional[asyncio.AbstractEventLoop]:
    """The loop set for this thread, without creating one (no deprecation warning)."""
    policy = asyncio.get_event_loop_policy()
    local = getattr(policy, "_local", None)
    return getattr(local, "_loop", None)


class EventLoopSweeper:
    """Collect the event loops replaced (not closed) during a test."""

    def __init__(self) -> None:
        self._loop_before: Any = None

    def before_test(self) -> None:
        self._loop_before = current_event_loop()

    def after_test(self) -> bool:
        """Collect garbage when the test replaced the thread's loop; True if it did."""
        loop = current_event_loop()
        replaced = loop is not self._loop_before
        self._loop_before = None
        if not replaced:
            return False
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            gc.collect()
        return True


QT_BINDINGS = ("PyQt6", "PyQt5", "PySide6")


def close_qt_windows() -> int:
    """Close the visible top-level widgets, run the deferred deletions; the number closed."""
    for binding in QT_BINDINGS:
        widgets = sys.modules.get(f"{binding}.QtWidgets")
        core = sys.modules.get(f"{binding}.QtCore")
        if widgets is None or core is None:
            continue
        app = widgets.QApplication.instance()
        if app is None:
            continue
        closed = 0
        for widget in widgets.QApplication.topLevelWidgets():
            if widget.isVisible():
                widget.close()
                closed += 1
        core.QCoreApplication.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)
        return closed
    return 0


class CrashBreadcrumb:
    """Write the running test's id to `path` (overwritten at each test)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)

    def running(self, nodeid: str) -> None:
        data = f"running: {nodeid}\n".encode()
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.ftruncate(self.fd, 0)
        os.write(self.fd, data)

    def finished(self) -> None:
        self.running("(session finished)")
        os.close(self.fd)
