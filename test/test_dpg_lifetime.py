"""Dear PyGui: a GUI object runs again after its first window was closed.

``run()`` releases the Dear PyGui context when the window closes, and any dpg
call without a context is a segmentation fault: a decorated
``@interactive_pipeline(gui="dpg")`` pipeline (one GUI object for every call)
crashed the process on its second call.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("interactive_pipe.graphical.dpg_gui")

SRC = Path(__file__).resolve().parents[1] / "src"

RUN_TWICE_SCRIPT = textwrap.dedent(
    """
    import numpy as np
    from interactive_pipe import interactive
    from interactive_pipe.graphical import dpg_backend
    from interactive_pipe.graphical.dpg_gui import InteractivePipeDPG
    from interactive_pipe.headless.pipeline import HeadlessPipeline

    dpg = dpg_backend.dpg
    # no display here: stub the viewport calls, keep the real widget tree
    for name in ("create_viewport", "set_viewport_resize_callback", "setup_dearpygui", "show_viewport",
                 "set_frame_callback"):
        setattr(dpg, name, lambda *_args, **_kwargs: None)
    dpg.is_dearpygui_running = lambda: False  # the window is closed at once
    dpg.get_viewport_client_width = lambda: 800
    dpg.get_viewport_client_height = lambda: 600

    @interactive(gain=(1.0, [0.0, 4.0]))
    def amplify(img, gain=1.0):
        return img * gain

    def pipe(img):
        out = amplify(img)
        return out

    gui = InteractivePipeDPG(pipeline=HeadlessPipeline.from_function(pipe, inputs=["img"]))
    gui.custom_end = lambda: None
    first_window = gui.window
    first = gui(np.ones((2, 2)))
    assert not dpg_backend.context_alive()  # released with the closed window
    second = gui(np.ones((2, 2)), gain=3.0)
    assert gui.window is not first_window  # a new window in a new context
    print("results", float(np.asarray(first[0]).max()), float(np.asarray(second[0]).max()))
    """
)


def test_a_dpg_gui_runs_again_after_its_window_was_closed(tmp_path):
    script = tmp_path / "run_twice.py"  # the pipeline source must be in a file
    script.write_text(RUN_TWICE_SCRIPT)
    env = dict(os.environ, PYTHONPATH=str(SRC), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    done = subprocess.run(
        [sys.executable, "-X", "faulthandler", str(script)], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr
    assert "results 1.0 3.0" in done.stdout
