"""Lifetime of the Qt background runner (InteractivePipeQT(threaded=True)).

Deleting a running QThread aborts the process ("QThread: Destroyed while
thread is still running", then `Fatal Python error: Aborted` with the
"Garbage-collecting" frame). A threaded window dropped without close() /
run() used to take its running worker with it when the garbage collector
reclaimed it.
"""

import gc
import os
import subprocess
import sys
import textwrap
import weakref
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.graphical import qt_runner  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"


@interactive(lifetime_gain=(1.0, [0.0, 2.0]))
def lifetime_amplify(img, lifetime_gain=1.0):
    return img * lifetime_gain


def lifetime_pipeline(img):
    out = lifetime_amplify(img)
    return out


def _threaded_gui():
    pipeline = HeadlessPipeline.from_function(lifetime_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="lifetime", size=(200, 100), threaded=True)
    gui.pipeline.inputs = [np.ones((4, 4))]
    return gui


def test_collecting_a_threaded_window_that_was_never_closed_does_not_abort(tmp_path):
    # in a fresh interpreter: before the fix this killed the whole process
    code = textwrap.dedent(
        """
        import gc
        import numpy as np
        from interactive_pipe import interactive
        from interactive_pipe.graphical.qt_gui import InteractivePipeQT
        from interactive_pipe.headless.pipeline import HeadlessPipeline

        @interactive(gain=(1.0, [0.0, 2.0]))
        def amplify(img, gain=1.0):
            return img * gain

        def pipe(img):
            out = amplify(img)
            return out

        gui = InteractivePipeQT(pipeline=HeadlessPipeline.from_function(pipe, inputs=["img"]), threaded=True)
        gui.pipeline.inputs = [np.ones((4, 4))]
        gui.window.request_refresh()  # a background run, then idle
        assert gui.window._runner.isRunning()
        del gui
        gc.collect()
        print("survived")
        """
    )
    env = dict(os.environ, PYTHONPATH=str(SRC), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    script = tmp_path / "dropped_threaded_window.py"  # the pipeline source must be in a file
    script.write_text(code)
    done = subprocess.run(
        [sys.executable, "-X", "faulthandler", str(script)], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr
    assert "survived" in done.stdout


def test_the_runner_ends_by_itself_when_its_window_is_collected():
    gui = _threaded_gui()
    runner = gui.window._runner
    window_ref = weakref.ref(gui.window)
    assert runner.isRunning() and runner in qt_runner._live_runners
    del gui
    gc.collect()
    assert window_ref() is None  # the runner does not keep its window alive
    assert runner.wait(5000)  # ... and stops once the window is gone
    runner.stop()  # idempotent, and forgets the runner
    assert runner not in qt_runner._live_runners


def test_stop_forgets_the_runner_and_finished_ones_are_pruned():
    gui = _threaded_gui()
    runner = gui.window._runner
    gui.window.stop_threaded_runs()
    assert not runner.isRunning()
    assert runner not in qt_runner._live_runners

    other = _threaded_gui()
    try:
        other_runner = other.window._runner
        qt_runner._live_runners.add(runner)  # a finished runner left behind
        other.window.stop_threaded_runs()
        other.window.start_threaded_runs()  # a new start prunes finished runners
        assert runner not in qt_runner._live_runners
        assert other_runner not in qt_runner._live_runners
    finally:
        other.window.stop_threaded_runs()


def test_a_plain_function_runner_still_runs():
    import threading

    app = qt_gui.QApplication.instance() or qt_gui.QApplication([])
    results = []
    runner = qt_runner.PipelineRunner(lambda: 42, threading.Lock())
    runner.run_finished.connect(results.append)
    runner.start()
    try:
        runner.request()
        for _ in range(500):
            app.processEvents()
            if results:
                break
            runner.wait(10)
        assert results == [42]
    finally:
        runner.stop()
