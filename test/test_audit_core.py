"""Regression tests for defects found by the November 2026 code audit (core)."""

import functools
import sys
from collections import namedtuple

import numpy as np
import pytest

from interactive_pipe import context, interactive, interactive_pipeline
from interactive_pipe.core import engine as engine_module
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.graph import PipelineSyntaxError
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.control_abbreviation import control_from_tuple

Box = namedtuple("Box", ["x", "y"])


def scale(img, a=1.0):
    return img * a


def maybe_fail(img, fail=False):
    if fail:
        raise RuntimeError("boom")
    return img + 1


def times_ten(img):
    return img * 10


def detect(img):
    return [Box(img, img + 1), Box(img + 2, img + 3)]


def count(boxes):
    return np.array([len(boxes), boxes[0].y[0]])


def test_graph_cache_is_not_stale_after_a_filter_error():
    def pipe(img):
        x = scale(img)
        y = maybe_fail(x)
        z = times_ten(x)
        return y, z

    pipeline = HeadlessPipeline.from_function(pipe, cache="graph")
    img = np.ones(2)
    pipeline(img)
    with pytest.raises(Exception, match="boom"):
        pipeline(img, a=2.0, fail=True)
    # `scale` was recomputed (and cached) by the failed run: `times_ten` must not
    # serve the result it computed before
    _, z = pipeline(img, fail=False)
    np.testing.assert_allclose(z, [20.0, 20.0])


def test_namedtuple_passed_between_filters():
    def pipe(img):
        boxes = detect(img)
        out = count(boxes)
        return out

    out = HeadlessPipeline.from_function(pipe)(np.zeros(1))
    np.testing.assert_allclose(out[0], [2, 1])


def test_pipeline_called_inside_a_filter_keeps_the_outer_context():
    def inner(img):
        out = times_ten(img)
        return out

    inner_pipeline = HeadlessPipeline.from_function(inner)
    seen = {}

    def outer_filter(img):
        context["before"] = 1
        res = inner_pipeline(img)
        context["after"] = 2  # the inner run must hand the context back
        seen.update(context)
        return res

    def outer(img):
        out = outer_filter(img)
        return out

    outer_pipeline = HeadlessPipeline.from_function(outer)
    np.testing.assert_allclose(outer_pipeline(np.ones(1))[0], [10.0])
    assert seen == {"before": 1, "after": 2}


def test_context_proxy_iter_and_len():
    seen = {}

    def reader(img):
        context["k"] = 1
        seen["keys"] = list(context)
        seen["len"] = len(context)
        return img

    def pipe(img):
        out = reader(img)
        return out

    HeadlessPipeline.from_function(pipe)(np.ones(1))
    assert "k" in seen["keys"]
    assert seen["len"] == len(seen["keys"])


def test_filter_core_call_explicit_kwarg_wins_over_control():
    @interactive(a=(1.0, [0.0, 3.0]))
    def scaled(img, a=1.0):
        return img * a

    np.testing.assert_allclose(scaled(np.ones(1), a=3.0), [3.0])
    filt = FilterCore(apply_fn=scale)
    filt.controls = {"a": control_from_tuple((1.0, [0.0, 3.0]), param_name="a")}  # type: ignore[attr-defined]
    np.testing.assert_allclose(filt(np.ones(1), a=3.0), [3.0])
    np.testing.assert_allclose(filt(np.ones(1)), [1.0])


def test_filter_core_accepts_a_partial():
    filt = FilterCore(apply_fn=functools.partial(scale, a=2.0))
    assert filt.name == "partial"


def test_excepthook_installed_once(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(engine_module, "_excepthook_installed", False)
    monkeypatch.setattr(engine_module, "_original_excepthook", sys.__excepthook__)
    engine_module._install_excepthook()
    ours = sys.excepthook
    saved = engine_module._original_excepthook

    def host_hook(*args):  # a host that chains to the hook it replaced (ours)
        ours(*args)

    sys.excepthook = host_hook
    engine_module._install_excepthook()
    # the host hook is neither replaced nor saved as "the original": no loop
    assert sys.excepthook is host_hook
    assert engine_module._original_excepthook is saved


def test_syntax_error_quotes_the_right_line_after_dedent_fallback():
    def pipe(img):
        """Docstring with a line
        less indented than the def."""
        out = img + 1
        return out

    with pytest.raises(PipelineSyntaxError) as info:
        interactive_pipeline(gui=None)(pipe)(np.ones(1))
    assert "out = img + 1" in str(info.value)
    assert "return out" not in str(info.value)


def test_ultra_short_list_rejects_extra_values():
    with pytest.raises(ValueError, match="at most 4"):
        control_from_tuple(([0, 10, 1, 7, 9],), param_name="x")
