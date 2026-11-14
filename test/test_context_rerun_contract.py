"""The context contract: a filter reading a key written by an earlier filter
re-runs whenever that filter re-runs (it sees the new value), in every cache
mode, also when none of its own inputs or parameters changed."""

import numpy as np
import pytest

from interactive_pipe import context, interactive
from interactive_pipe.headless.pipeline import HeadlessPipeline

CALLS = []


@interactive()
def segment(img, method=("otsu", ["otsu", "fixed"])):
    CALLS.append("segment")
    context["threshold"] = 0.5 if method == "fixed" else float(img.mean())
    return img > context["threshold"]  # reads back its own value: not a feedback loop


@interactive()
def histogram(img, bins=(8, [2, 16])):
    CALLS.append("histogram")
    return np.array([context["threshold"], float(bins)])


def contract_pipeline(img):
    mask = segment(img)
    hist = histogram(img)  # does not take `mask`: depends on segment through context only
    return mask, hist


@pytest.mark.parametrize("cache", [False, True, "graph"])
def test_reader_reruns_when_the_writer_does(cache):
    img = np.linspace(0, 0.8, 16).reshape(4, 4)
    pipe = HeadlessPipeline.from_function(contract_pipeline, cache=cache)
    CALLS.clear()
    _, hist = pipe(img, method="otsu")
    assert hist[0] == pytest.approx(0.4)
    _, hist = pipe(img, method="fixed")
    assert hist[0] == 0.5  # not the stale 0.4
    assert CALLS.count("histogram") == 2
    if cache:
        CALLS.clear()
        pipe.parameters = {"histogram": {"bins": 4}}  # only the reader's own parameter
        _, hist = pipe.run()
        assert CALLS == ["histogram"] and hist[0] == 0.5  # the writer is cached, its key still there
