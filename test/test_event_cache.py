"""Key-bound events only invalidate the filters that read them."""

import matplotlib

matplotlib.use("Agg")

from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from interactive_pipe import events, interactive  # noqa: E402
from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)
RUNS = {"heavy": 0, "reader": 0, "independent": 0}


@interactive(heavy_gain=(1.0, [0.0, 2.0]))
def ev_heavy(img, heavy_gain=1.0):
    RUNS["heavy"] += 1
    return img * heavy_gain


@interactive()
def ev_reader(img):
    RUNS["reader"] += 1
    return 1.0 - img if events.get("flip") else img


@interactive()
def ev_independent(img):
    RUNS["independent"] += 1
    return img * 0.5


def event_cache_pipeline(img):
    heavy = ev_heavy(img)
    flipped = ev_reader(heavy)
    other = ev_independent(img)
    return flipped, other


def _reset_runs():
    for key in RUNS:
        RUNS[key] = 0


@pytest.mark.parametrize("cache", [True, "graph"])
def test_key_event_only_reruns_readers(cache):
    _reset_runs()
    pipeline = HeadlessPipeline.from_function(event_cache_pipeline, inputs=["img"], cache=cache)
    gui = InteractivePipeMatplotlib(pipeline=pipeline, name=f"event cache {cache}")
    gui.bind_key_to_context("f", "flip", "flip the image")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    assert RUNS == {"heavy": 1, "reader": 1, "independent": 1}
    assert pipeline.framework_state.event_readers["flip"] == {"ev_reader"}
    _reset_runs()
    gui.on_press(SimpleNamespace(key="f"))  # matplotlib key event
    # the reader reran with the event raised, the upstream heavy filter did not
    assert RUNS["reader"] == 1 and RUNS["heavy"] == 0
    assert RUNS["independent"] == (1 if cache is True else 0)  # prefix cache recomputes what follows
    np.testing.assert_allclose(pipeline.results[0][0], 1.0 - INPUT_IMAGE)
    gui.close()


def test_unknown_event_reader_falls_back_to_full_reset():
    _reset_runs()
    pipeline = HeadlessPipeline.from_function(event_cache_pipeline, inputs=["img"], cache=True)
    gui = InteractivePipeMatplotlib(pipeline=pipeline, name="event fallback")
    gui.bind_key_to_context("x", "never_read", "unused event")
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    gui.window.refresh()
    _reset_runs()
    gui.on_press(SimpleNamespace(key="x"))
    assert RUNS == {"heavy": 1, "reader": 1, "independent": 1}
    gui.close()
