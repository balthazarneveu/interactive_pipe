"""@interactive filters called directly, like plain functions (unit tests).

layout / audio calls do nothing, events are off, the context is a scratch dict
for the duration of the call; outside any filter the calls still raise.
"""

import numpy as np
import pytest

from interactive_pipe import audio, context, events, interactive, layout
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(gain=(1.0, [0.0, 2.0]))
def dc_compare(out, gt, gain=1.0):
    layout.style("error", title="error", colormap="magma", colorbar=True)
    layout.grid([["out", "error"]])
    context["psnr"] = -10 * np.log10(np.mean((out - gt) ** 2) + 1e-12)
    audio.stop()
    boost = 2.0 if events.get("boost") else 1.0
    return np.abs(out - gt) * gain * boost


def test_direct_call_runs():
    out, gt = np.ones((4, 4)), np.zeros((4, 4))
    np.testing.assert_array_equal(dc_compare(out, gt), np.ones((4, 4)))
    np.testing.assert_array_equal(dc_compare(out, gt, gain=0.5), 0.5 * np.ones((4, 4)))


def test_scratch_context_does_not_outlive_the_call():
    @interactive()
    def dc_counter(x):
        context["n"] = context.get("n", 0) + 1
        return context["n"]

    assert dc_counter(0) == 1
    assert dc_counter(0) == 1  # a new scratch dict per call


def test_missing_key_read_says_why():
    @interactive()
    def dc_reader(x):
        return x * context["scale"]

    with pytest.raises(KeyError, match=r"context\['scale'\] is not set: 'dc_reader' is called directly"):
        dc_reader(1.0)


def test_layout_calls_are_still_validated():
    @interactive()
    def dc_bad_style(x):
        layout.style("x", colormap="viridiss")
        return x

    with pytest.raises(ValueError, match="unknown colormap"):
        dc_bad_style(1.0)


def test_inside_a_pipeline_nothing_changes():
    @interactive()
    def dc_write(x):
        context["scale"] = 3.0
        return x

    @interactive()
    def dc_read(x):
        return x * context["scale"]

    def pipe(x):
        y = dc_write(x)
        z = dc_read(y)
        return z

    pipeline = HeadlessPipeline.from_function(pipe, inputs=["x"])
    assert pipeline(2.0)[0] == 6.0
    assert pipeline._user_context["scale"] == 3.0


def test_outside_any_filter_still_raises():
    with pytest.raises(
        RuntimeError, match=r"layout.style\('x', \.\.\.\) called outside .*called directly like a plain"
    ):
        layout.style("x", title="x")
    with pytest.raises(RuntimeError, match=r"context\['a'\] = \.\.\. called outside"):
        context["a"] = 1


def test_undecorated_function_still_raises():
    def plain(x):
        layout.style("x", title="x")
        return x

    with pytest.raises(RuntimeError, match="@interactive filter"):
        plain(1.0)
