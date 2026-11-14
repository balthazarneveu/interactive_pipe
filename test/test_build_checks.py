"""Small build / export checks: pointer targets at build time, animation errors name the output."""

import logging

import numpy as np
import pytest

from interactive_pipe import PointControl, TimeControl, interactive, interactive_pipeline
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(where=PointControl((0.5, 0.5), on="missing"))
def bc_misplaced(img, where=(0.5, 0.5)):
    return img


def test_unknown_pointer_target_fails_at_build_with_a_gui():
    def bad(img):
        out = bc_misplaced(img)
        return [img, out]

    with pytest.raises(ValueError, match=r"on='missing' is not an output of pipeline 'bad'"):
        interactive_pipeline(gui="qt")(bad)


def test_unknown_pointer_target_only_warns_without_a_gui(caplog):
    def small_test_pipeline(img):
        out = bc_misplaced(img)
        return out

    with caplog.at_level(logging.WARNING):
        pipe = interactive_pipeline(gui=None)(small_test_pipeline)
    assert "on='missing' is not an output" in caplog.text and "a GUI would raise" in caplog.text
    assert np.asarray(pipe(np.ones((2, 2)))).sum() == 4  # runs, the control keeps its value


@interactive(t=TimeControl())
def bc_channel_first(t=0.0):
    return np.zeros((3, 8, 8))  # channel-first: cannot be displayed


def test_animation_display_error_names_the_output(tmp_path):
    from interactive_pipe.graphical.display import DisplayError
    from interactive_pipe.headless.animation import export_animation

    def anim():
        frame = bc_channel_first()
        return frame

    pipe = HeadlessPipeline.from_function(anim, inputs=[])
    pipe.inputs = []
    with pytest.raises(DisplayError, match=r"frame.*bc_channel_first|bc_channel_first.*frame"):
        export_animation(pipe, tmp_path / "a.gif", duration=0.2, fps=5)
