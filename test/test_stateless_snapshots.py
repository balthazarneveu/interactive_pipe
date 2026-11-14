"""Snapshots and sweeps of stateful pipelines start from a fresh context.

Reproducer of the dogfooding log (item 4): a filter advancing a counter in the
context made every snapshot / sweep cell depend on the runs before it.
"""

import numpy as np
import pytest

from interactive_pipe import context, events, interactive
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def st_count(gain=1.0):
    context["n"] = context.get("n", 0) + 1  # `gain` is unused on purpose
    return np.full((8, 8), context["n"] / 10)


def st_pipeline():
    counted = st_count()
    return counted


def _pipe(**kwargs):
    return HeadlessPipeline.from_function(st_pipeline, inputs=[], **kwargs)


def test_snapshots_do_not_depend_on_earlier_runs():
    pipe = _pipe()
    means = [pipe.snapshot(None, gain=gain, caption=False).mean() for gain in (1.0, 2.0, 3.0)]
    assert means[0] == means[1] == means[2]


def test_sweep_cells_are_independent_and_reproducible():
    pipe = _pipe()
    first = pipe.sweep(None, gain=[1.0, 2.0, 3.0], caption=False)
    pipe()
    pipe()  # the live state moves on
    np.testing.assert_array_equal(pipe.sweep(None, gain=[1.0, 2.0, 3.0], caption=False), first)


def test_live_context_untouched():
    pipe = _pipe()
    pipe()
    pipe()
    assert pipe._user_context["n"] == 2
    pipe.snapshot(None)
    pipe.sweep(None, gain=[1.0, 2.0])
    assert pipe._user_context["n"] == 2
    (out,) = pipe()  # continues from the live state, not from the snapshot's
    assert out[0, 0] == pytest.approx(0.3)


def test_snapshot_starts_from_the_context_given_from_outside():
    pipe = _pipe(context={"n": 10})
    pipe()
    pipe(context={"n": 20})  # given from outside: part of the starting state
    assert pipe._user_context["n"] == 21
    image = pipe.snapshot(None, caption=False, output=0)
    one_run = _pipe(context={"n": 20}).snapshot(None, caption=False, output=0)
    np.testing.assert_array_equal(image, one_run)
    assert pipe._user_context["n"] == 21


def test_warm_up_runs():
    pipe = _pipe()
    warm = pipe.snapshot(None, caption=False, runs=5)
    expected = _pipe()
    for _ in range(4):
        expected()
    np.testing.assert_array_equal(warm, expected.snapshot(None, caption=False, runs=5))
    assert warm.mean() > pipe.snapshot(None, caption=False).mean()
    with pytest.raises(ValueError, match="runs must be a positive int"):
        pipe.snapshot(None, runs=0)
    with pytest.raises(ValueError, match="runs must be a positive int"):
        pipe.sweep(None, gain=[1.0, 2.0], runs=1.5)


@interactive()
def st_event_reader():
    return np.full((4, 4), 1.0 if events.get("boost") else 0.0)


def st_event_pipeline():
    shown = st_event_reader()
    return shown


def test_events_start_off_and_are_restored():
    pipe = HeadlessPipeline.from_function(st_event_pipeline, inputs=[])
    pipe.framework_state.events["boost"] = True  # a key was pressed in the live session
    assert pipe()[0][0, 0] == 1.0
    from interactive_pipe.headless.explore import run_snapshot

    _, result = run_snapshot(pipe, None, caption=False)
    assert result[0][0, 0] == 0.0  # rendered with the event off
    assert pipe.framework_state.events["boost"] is True
    assert pipe()[0][0, 0] == 1.0
