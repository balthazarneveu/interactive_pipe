"""Background pipeline runs for the Qt backend (opt-in ``threaded=True``).

A single worker thread runs the pipeline; requests coalesce (latest wins):
however many parameter changes arrive while a run is in progress, exactly one
more run follows it, with the values current at that time. Results come back
to the GUI thread through a queued signal, so widgets stay live while a slow
pipeline computes.

Lifetime: Qt aborts the whole process ("QThread: Destroyed while thread is
still running") when a running QThread is deleted. A window dropped without
``close()`` / ``run()`` (a script or a test building a ``threaded=True`` GUI and
never showing it) is deleted by Python's garbage collector, which would take
its runner with it. So a started runner is kept alive by a module registry
(not by the window) until it has stopped, and it holds the run function
weakly: when the window is collected, the runner ends on its own.
"""

import atexit
import inspect
import logging
import threading
import weakref
from typing import Any, Callable, Set

from interactive_pipe.graphical.qt_backend import QThread, Signal


class PipelineRunner(QThread):  # type: ignore[reportGeneralTypeIssues]
    """Worker thread calling `run_fn` on request.

    `run_fn` runs the pipeline and returns whatever the GUI needs to display
    it (it should catch pipeline errors itself); its return value is emitted
    through `run_finished`, received in the GUI thread. `run_lock` serializes
    worker runs with synchronous runs from the GUI thread (key events,
    resets), so two runs never overlap.
    """

    run_finished = Signal(object)

    def __init__(self, run_fn: Callable[[], Any], run_lock: threading.Lock, parent=None) -> None:
        super().__init__(parent)
        self._wake = threading.Condition()
        self._requested = False
        self._stopping = False
        self._busy = False
        self._run_lock = run_lock
        # weak for bound methods: the runner must not keep its window alive, and
        # the window being collected stops the runner (no wait: GC may run anywhere)
        if inspect.ismethod(run_fn):
            self._run_fn: Callable[[], Any] = weakref.WeakMethod(run_fn, lambda _ref: self._ask_to_stop())  # type: ignore[arg-type]
        else:
            self._run_fn = lambda: run_fn

    def start(self, *args) -> None:  # type: ignore[override]
        """Start the thread; it stays referenced by the module until it ends."""
        _prune_finished_runners()
        _live_runners.add(self)
        super().start(*args)

    @property
    def busy(self) -> bool:
        """True while a run is in progress or requested."""
        with self._wake:
            return self._busy or self._requested

    def request(self) -> None:
        """Ask for a run; requests made during a run collapse into one more run."""
        with self._wake:
            self._requested = True
            self._wake.notify()

    def _ask_to_stop(self) -> None:
        with self._wake:
            self._stopping = True
            self._wake.notify()

    def stop(self) -> None:
        """Let the current run finish, then end the thread. Idempotent."""
        self._ask_to_stop()
        if self.isRunning():
            self.wait()
        _live_runners.discard(self)

    def run(self) -> None:  # executed in the worker thread
        while True:
            with self._wake:
                while not self._requested and not self._stopping:
                    self._wake.wait()
                if self._stopping:
                    return
                self._requested = False
                self._busy = True
            run_fn = self._run_fn()
            if run_fn is None:  # the window was garbage collected
                with self._wake:
                    self._busy = False
                return
            try:
                with self._run_lock:
                    result = run_fn()
            except Exception:
                # Broad on purpose: never let the worker thread die silently;
                # the error is logged and the next request runs again.
                logging.exception("Background pipeline run failed")
                continue
            finally:
                run_fn = None  # do not keep the window alive while idle
                with self._wake:
                    self._busy = False
            self.run_finished.emit(result)
            del result


# Started runners, referenced until they have stopped (see the module docstring).
_live_runners: Set[PipelineRunner] = set()


def _prune_finished_runners() -> None:
    """Drop the runners whose thread has ended (called from the GUI thread)."""
    for runner in list(_live_runners):
        if runner.isFinished():
            _live_runners.discard(runner)


@atexit.register
def _stop_live_runners() -> None:
    # before the interpreter tears the module down: never delete a running QThread
    for runner in list(_live_runners):
        runner.stop()
