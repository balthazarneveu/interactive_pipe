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


def test_colliding_auto_named_controls_are_disambiguated_by_filter():
    # GUI widgets are keyed by control name: two filters both declaring a
    # "coeff" control get labels saying which filter they drive.
    pipeline = HeadlessPipeline.from_function(colliding_pipeline, inputs=["img"])
    assert [ctrl.name for ctrl in pipeline.controls] == ["stage_one.coeff", "stage_two.coeff"]
    assert pipeline.controls[0].filter_to_connect is pipeline.filters[0]
    assert pipeline.controls[1].filter_to_connect is pipeline.filters[1]
    pipeline.controls[0].update(0.25)
    pipeline.controls[1].update(1.0)
    (result,) = pipeline(np.ones((2, 2)))
    assert np.allclose(result, 0.25 + 1.0)
    # a pipeline keyword sets the parameter in every filter having it...
    (result,) = pipeline(np.ones((2, 2)), coeff=0.5)
    assert np.allclose(result, 0.5 + 0.5)
    # ...and parameters= targets one filter
    (result,) = pipeline(np.ones((2, 2)), parameters={"stage_two": {"coeff": 0.0}})
    assert np.allclose(result, 0.5)


def test_disambiguation_does_not_leak_into_the_registry_or_other_pipelines():
    first = HeadlessPipeline.from_function(colliding_pipeline, inputs=["img"])
    # the shared registered controls keep their names
    assert Control.get_controls(stage_one)["coeff"].name == "coeff"
    assert Control.get_controls(stage_two)["coeff"].name == "coeff"

    def only_stage_one(img):
        out = stage_one(img)
        return out

    alone = HeadlessPipeline.from_function(only_stage_one)
    assert [ctrl.name for ctrl in alone.controls] == ["coeff"]
    # notebook re-run: same names again
    again = HeadlessPipeline.from_function(colliding_pipeline, inputs=["img"])
    assert [ctrl.name for ctrl in again.controls] == [ctrl.name for ctrl in first.controls]


def test_repeated_and_colliding_filters_all_named_by_filter_instance():
    def mixed(img):
        a = stage_one(img)
        b = stage_one(a)
        c = stage_two(b)
        return c

    pipeline = HeadlessPipeline.from_function(mixed)
    assert [ctrl.name for ctrl in pipeline.controls] == [
        "stage_one.coeff",
        "stage_one_1.coeff",
        "stage_two.coeff",
    ]


@interactive(coeff=Control(0.5, [0.0, 1.0], name="coeff"))
def explicit_one(img, coeff=0.5):
    return img * coeff


@interactive(coeff=Control(0.5, [0.0, 1.0], name="coeff"))
def explicit_two(img, coeff=0.5):
    return img + coeff


def test_explicitly_named_colliding_controls_still_raise():
    def explicit_pipeline(img):
        mid = explicit_one(img)
        out = explicit_two(mid)
        return out

    with pytest.raises(ValueError, match="Duplicate control name 'coeff'"):
        HeadlessPipeline.from_function(explicit_pipeline)


def test_explicit_name_wins_over_an_auto_named_collision():
    def explicit_and_auto(img):
        mid = explicit_one(img)
        out = stage_two(mid)
        return out

    pipeline = HeadlessPipeline.from_function(explicit_and_auto)
    assert [ctrl.name for ctrl in pipeline.controls] == ["coeff", "stage_two.coeff"]


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


# --- process state: two scripts in one interpreter, pipelines sharing a filter ---------------

SCRIPT_A = """
from interactive_pipe import interactive

@interactive(hue_shift=(0.0, [-1.0, 1.0]))
def process_image(img, hue_shift=0.0):
    return img + hue_shift

def pipe_a(img):
    out = process_image(img)
    return out
"""

SCRIPT_B = """
from interactive_pipe import interactive

@interactive(gain=(1.0, [0.0, 2.0]))
def process_image(img, gain=1.0):
    return img * gain

def pipe_b(img):
    out = process_image(img)
    return out
"""


def test_two_main_scripts_with_same_named_filters_do_not_collide(tmp_path):
    # both scripts define `__main__.process_image`: the registry used to be keyed
    # by module + qualname, so the second definition replaced the first one's
    # controls (`filter 'process_image' has no parameter 'hue_shift'`)
    import runpy

    (tmp_path / "a.py").write_text(SCRIPT_A)
    (tmp_path / "b.py").write_text(SCRIPT_B)
    a = runpy.run_path(str(tmp_path / "a.py"), run_name="__main__")
    b = runpy.run_path(str(tmp_path / "b.py"), run_name="__main__")
    pipe_a = HeadlessPipeline.from_function(a["pipe_a"])
    pipe_b = HeadlessPipeline.from_function(b["pipe_b"])
    assert [ctrl.name for ctrl in pipe_a.controls] == ["hue_shift"]
    assert [ctrl.name for ctrl in pipe_b.controls] == ["gain"]
    (result,) = pipe_a(np.zeros((2, 2)), hue_shift=0.5)
    assert np.allclose(result, 0.5)
    (result,) = pipe_b(np.ones((2, 2)), gain=2.0)
    assert np.allclose(result, 2.0)


def test_filters_made_by_a_factory_keep_their_own_controls():
    def make(default):
        @interactive(gain=(default, [0.0, 4.0]))
        def scaled(img, gain=default):
            return img * gain

        return scaled

    one, three = make(1.0), make(3.0)  # same module, same qualname
    assert Control.get_controls(one)["gain"].value_default == 1.0
    assert Control.get_controls(three)["gain"].value_default == 3.0
    assert one(np.ones(1))[0] == 1.0 and three(np.ones(1))[0] == 3.0


@interactive(level=(1.0, [0.0, 4.0]))
def shared_level(img, level=1.0):
    return img * level


def shared_pipeline_one(img):
    out = shared_level(img)
    return out


def shared_pipeline_two(img):
    out = shared_level(img)
    return out


def test_pipelines_built_from_one_filter_do_not_share_its_control():
    """Each pipeline owns clones of the declared controls: a value set in one
    pipeline does not leak into another one, nor into direct calls."""
    first = HeadlessPipeline.from_function(shared_pipeline_one)
    second = HeadlessPipeline.from_function(shared_pipeline_two)
    declared = Control.get_controls(shared_level)["level"]
    assert first.controls[0] is not second.controls[0]
    assert declared not in (first.controls[0], second.controls[0])
    first.controls[0].update(2.0)
    assert second.controls[0].value == 1.0
    assert np.allclose(first(np.ones(1))[0], 2.0)
    assert np.allclose(second(np.ones(1))[0], 1.0)
    assert np.allclose(shared_level(np.ones(1)), 1.0)  # direct call: the declared default
    assert declared.value == 1.0 and declared.filter_to_connect is None
    # a pipeline built later starts from the declared default
    assert HeadlessPipeline.from_function(shared_pipeline_one).controls[0].value == 1.0
