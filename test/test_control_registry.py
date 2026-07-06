"""Control registry scoping: cross-module keys, per-function name uniqueness,
duplicate-name detection at pipeline construction."""

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.pipeline import HeadlessPipeline


def make_local_gain_filter():
    """Return a filter whose function shares its __name__ with module-level
    `gain_filter` below but has a distinct __qualname__ (different "module path")."""

    @interactive(gain=(2.0, [0.0, 4.0]))
    def gain_filter(img, gain=2.0):
        return img * gain

    return gain_filter


@interactive(gain=(1.0, [0.0, 2.0]))
def gain_filter(img, gain=1.0):
    return img * gain


# Filters and pipeline functions used by the pipeline-construction tests below.
# They must live at module level: the AST parser reads the pipeline source.
@interactive(coeff=(0.5, [0.0, 1.0]))
def stage_one(img, coeff=0.5):
    return img * coeff


@interactive(coeff=(0.5, [0.0, 1.0]))
def stage_two(img, coeff=0.5):
    return img + coeff


def colliding_pipeline(img):
    mid = stage_one(img)
    out = stage_two(mid)
    return out


@interactive(brightness=(0.5, [0.0, 1.0]))
def brighten(img, brightness=0.5):
    return img * brightness


@interactive(offset=(0.1, [0.0, 1.0]))
def shift(img, offset=0.1):
    return img + offset


def two_stage_pipeline(img):
    mid = brighten(img)
    out = shift(mid)
    return out


@interactive(amount=(0.5, [0.0, 1.0]))
def scale(img, amount=0.5):
    return img * amount


def repeated_pipeline(img):
    a = scale(img)
    b = scale(a)
    return b


@interactive(kb_toggle=KeyboardControl(False, keydown="k"))
def kb_filter(img, kb_toggle=False):
    return 1.0 - img if kb_toggle else img


def repeated_kb_pipeline(img):
    a = kb_filter(img)
    b = kb_filter(a)
    return b


def test_same_param_name_in_two_filters_does_not_raise():
    # Control-name uniqueness is scoped per decorated function: two filters
    # may freely share a parameter name.
    @interactive(coeff=(0.5, [0.0, 1.0]))
    def first(img, coeff=0.5):
        return img * coeff

    @interactive(coeff=(0.5, [0.0, 1.0]))
    def second(img, coeff=0.5):
        return img + coeff


def test_redecorating_same_function_does_not_raise():
    # Notebook cell re-run: decorating the same source function repeatedly
    # must not accumulate state and trip the uniqueness check.
    def base(img, amount=0.3):
        return img * amount

    for _ in range(3):
        interactive(amount=(0.3, [0.0, 1.0]))(base)


def test_duplicate_control_names_within_one_filter_still_raise():
    with pytest.raises(ValueError, match="already attributed"):

        @interactive(
            a=Control(0.5, [0.0, 1.0], name="shared"),
            b=Control(0.2, [0.0, 1.0], name="shared"),
        )
        def conflicted(img, a=0.5, b=0.2):
            return img * a + b


def test_same_function_name_in_different_scopes_no_registry_collision():
    other_gain_filter = make_local_gain_filter()
    module_level_controls = Control.get_controls(gain_filter)
    local_controls = Control.get_controls(other_gain_filter)
    assert module_level_controls["gain"].value_default == 1.0
    assert local_controls["gain"].value_default == 2.0
    assert module_level_controls["gain"] is not local_controls["gain"]


def test_get_controls_rejects_bare_names():
    with pytest.raises(TypeError):
        Control.get_controls("gain_filter")


def test_duplicate_control_names_across_filters_raise_at_pipeline_build():
    # GUI widgets are keyed by control name: two distinct controls named
    # "coeff" in one pipeline must fail loudly at construction.
    with pytest.raises(ValueError, match="Duplicate control name 'coeff'"):
        HeadlessPipeline.from_function(colliding_pipeline, inputs=["img"])


def test_distinct_control_names_across_filters_build_and_run():
    pipeline = HeadlessPipeline.from_function(two_stage_pipeline, inputs=["img"])
    control_names = sorted(ctrl.name for ctrl in pipeline.controls)
    assert control_names == ["brightness", "offset"]
    img = np.ones((2, 2))
    (result,) = pipeline(img)
    assert np.allclose(result, img * 0.5 + 0.1)


def test_repeated_filter_gets_per_instance_control_clones():
    # Using one decorated filter twice yields one control per instance: the
    # original drives the first filter, a suffixed clone drives the repeat.
    pipeline = HeadlessPipeline.from_function(repeated_pipeline, inputs=["img"])
    assert [filt.name for filt in pipeline.filters] == ["scale", "scale_1"]
    assert [ctrl.name for ctrl in pipeline.controls] == ["amount", "amount_1"]
    assert pipeline.controls[0].filter_to_connect is pipeline.filters[0]
    assert pipeline.controls[1].filter_to_connect is pipeline.filters[1]
    # both instances are driven independently
    pipeline.controls[0].update(0.5)
    pipeline.controls[1].update(0.25)
    img = np.ones((2, 2))
    (result,) = pipeline(img)
    assert np.allclose(result, img * 0.5 * 0.25)


def test_repeated_filter_keyboard_control_stays_on_first_instance():
    # Pinned: key-bound controls are not cloned (their key bindings would
    # collide), so the repeat runs with default values.
    pipeline = HeadlessPipeline.from_function(repeated_kb_pipeline, inputs=["img"])
    assert [filt.name for filt in pipeline.filters] == ["kb_filter", "kb_filter_1"]
    assert len(pipeline.controls) == 1
    assert pipeline.controls[0].filter_to_connect is pipeline.filters[0]
