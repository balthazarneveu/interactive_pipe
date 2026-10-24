"""Background pipeline runs for the Qt backend (opt-in ``threaded=True``).

A single worker thread runs the pipeline; requests coalesce (latest wins):
however many parameter changes arrive while a run is in progress, exactly one
more run follows it, with the values current at that time. Results come back
to the GUI thread through a queued signal, so widgets stay live while a slow
pipeline computes.
"""

import logging
import threading
from typing import Any, Callable

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
        self._run_fn = run_fn
        self._run_lock = run_lock
        self._wake = threading.Condition()
        self._requested = False
        self._stopping = False
        self._busy = False

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

    def stop(self) -> None:
        """Let the current run finish, then end the thread. Idempotent."""
        with self._wake:
            self._stopping = True
            self._wake.notify()
        if self.isRunning():
            self.wait()

    def run(self) -> None:  # executed in the worker thread
        while True:
            with self._wake:
                while not self._requested and not self._stopping:
                    self._wake.wait()
                if self._stopping:
                    return
                self._requested = False
                self._busy = True
            try:
                with self._run_lock:
                    result = self._run_fn()
            except Exception:
                # Broad on purpose: never let the worker thread die silently;
                # the error is logged and the next request runs again.
                logging.exception("Background pipeline run failed")
                continue
            finally:
                with self._wake:
                    self._busy = False
            self.run_finished.emit(result)
