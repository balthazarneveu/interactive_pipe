"""A bare filter call drops what the filter returns; DisplayError is exported."""

import numpy as np
import pytest

import interactive_pipe
from interactive_pipe import interactive
from interactive_pipe.headless.pipeline import HeadlessPipeline

SEEN = []


@interactive()
def doubled(img):
    SEEN.append(float(img.sum()))
    return img * 2


@interactive()
def pair(img):
    return img, img


def bare_pipeline(img):
    doubled(img)  # result not assigned: dropped
    pair(img)
    return img


def test_bare_call_runs_and_drops_the_value():
    SEEN.clear()
    out = HeadlessPipeline.from_function(bare_pipeline)(np.ones((2, 2)))
    assert SEEN == [4.0]
    np.testing.assert_array_equal(np.asarray(out).reshape(2, 2), np.ones((2, 2)))


def test_display_error_is_exported():
    from interactive_pipe.graphical.display import DisplayError

    assert interactive_pipe.DisplayError is DisplayError
    assert "DisplayError" in interactive_pipe.__all__
    assert issubclass(DisplayError, ValueError)
    with pytest.raises(interactive_pipe.DisplayError):
        from interactive_pipe.graphical.display import check_displayable

        check_displayable(np.zeros((3, 8, 8)), name="out")
