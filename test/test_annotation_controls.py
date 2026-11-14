"""Controls declared by a filter's own annotations (Annotated / Literal / Enum)."""

import enum
from typing import Annotated, Literal, Tuple

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.headless.control import (
    CircularControl,
    Control,
    MappedChoiceControl,
    RangeControl,
    TextPrompt,
    TimeControl,
)
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.pipeline import HeadlessPipeline


class Style(enum.Enum):
    FLAT = 1
    GLOSSY = 2


class Color(str, enum.Enum):
    RED = "r"
    GREEN = "g"


def _controls(pipe):
    return {ctrl.name: ctrl for ctrl in pipe.controls}


def _build(filt):
    def pipe(img):
        out = filt(img)
        return out

    return HeadlessPipeline.from_function(pipe)


IMG = np.ones((2, 2))


# --- opt-in rules ----------------------------------------------------------------


def test_annotated_numeric_bool_literal_enum_make_widgets():
    @interactive()
    def adjust(
        img,
        gain: Annotated[float, (0.0, 3.0)] = 1.0,
        radius: Annotated[int, (1, 15, 2), "Blur radius"] = 3,
        flip: Annotated[bool, "Flip"] = False,
        mode: Literal["dark", "light"] = "light",
        style: Style = Style.GLOSSY,
    ):
        return img * gain

    controls = Control.get_controls(adjust)
    assert set(controls) == {"gain", "radius", "flip", "mode", "style"}
    gain = controls["gain"]
    assert (gain.value_default, gain.value_range, gain._type) == (1.0, [0.0, 3.0], float)
    radius = controls["radius"]
    assert (radius.name, radius.value_range, radius.step, radius._type) == ("Blur radius", [1, 15], 2, int)
    assert controls["flip"].name == "Flip" and controls["flip"]._type is bool
    assert (controls["mode"].value_default, controls["mode"].value_range) == ("light", ["dark", "light"])
    assert isinstance(controls["style"], MappedChoiceControl)
    assert (controls["style"].value_default, controls["style"].value_range) == ("GLOSSY", ["FLAT", "GLOSSY"])


def test_plain_hints_make_no_widget():
    @interactive()
    def plain(img, gain: float = 1.0, flip: bool = False, name: str = "a", n: int = 3):
        return img

    assert Control.get_controls(plain) == {}


def test_foreign_annotated_metadata_makes_no_widget():
    class Unit:
        pass

    @interactive()
    def foreign(img, gain: Annotated[float, Unit()] = 1.0, flip: Annotated[bool, Unit()] = False):
        return img

    assert Control.get_controls(foreign) == {}


def test_label_without_range_warns_and_makes_no_widget(caplog):
    @interactive()
    def doc_only(img, gain: Annotated[float, "gain in dB"] = 1.0):
        return img

    assert Control.get_controls(doc_only) == {}
    assert "without a range" in caplog.text


def test_group_as_second_label():
    @interactive()
    def grouped(img, gain: Annotated[float, (0.0, 3.0), "Gain", "Exposure"] = 1.0):
        return img

    ctrl = Control.get_controls(grouped)["gain"]
    assert ctrl.name == "Gain"
    assert ctrl.panel is not None and ctrl.panel.name == "Exposure"


def test_string_choices_and_range_control():
    @interactive()
    def pick(
        img,
        mode: Annotated[str, ["a", "b", "c"]] = "b",
        window: Annotated[Tuple[float, float], (0.0, 1.0)] = (0.2, 0.8),
    ):
        return img

    controls = Control.get_controls(pick)
    assert controls["mode"].value_range == ["a", "b", "c"] and controls["mode"].value_default == "b"
    assert isinstance(controls["window"], RangeControl)
    assert controls["window"].value_default == (0.2, 0.8)


def test_int_default_for_float_hint_is_coerced():
    @interactive()
    def coerce(img, gain: Annotated[float, (0, 3)] = 1):
        return img

    ctrl = Control.get_controls(coerce)["gain"]
    assert ctrl._type is float and ctrl.value_default == 1.0


# --- Control instances in annotations ----------------------------------------------


@pytest.mark.parametrize(
    "ctrl, default",
    [
        (CircularControl(0.0, [0.0, 360.0]), 0.0),
        (KeyboardControl(1.0, [0.0, 3.0], keydown="g", keyup="h"), 1.0),
        (RangeControl((0.1, 0.9), [0.0, 1.0]), (0.1, 0.9)),
        (TextPrompt("hello"), "hello"),
        (TimeControl(), 0.0),
        (Control(2, [0, 5]), 2),
    ],
)
def test_control_subclasses_in_annotation(ctrl, default):
    @interactive()
    def with_control(img, param: Annotated[object, ctrl] = default):
        return img

    found = Control.get_controls(with_control)["param"]
    assert type(found) is type(ctrl)
    assert found is not ctrl  # per-function clone
    assert found.name == "param"
    assert found.value_default == ctrl.value_default


def test_shared_annotation_alias_is_not_shared_between_functions():
    Gain = Annotated[float, Control(1.0, [0.0, 3.0])]

    @interactive()
    def first(img, gain: Gain = 1.0):
        return img * gain

    @interactive()
    def second(img, gain: Gain = 2.0):
        return img * gain

    c1, c2 = Control.get_controls(first)["gain"], Control.get_controls(second)["gain"]
    assert c1 is not c2
    assert (c1.value_default, c2.value_default) == (1.0, 2.0)

    def pipe(img):
        a = first(img)
        b = second(a)
        return b

    p1 = HeadlessPipeline.from_function(pipe)
    p2 = HeadlessPipeline.from_function(pipe)
    assert sorted(_controls(p1)) == ["first.gain", "second.gain"]
    assert sorted(_controls(p2)) == ["first.gain", "second.gain"]
    p1(IMG, parameters={"first": {"gain": 3.0}})
    assert p1(IMG)[0][0, 0] == 6.0
    assert _controls(p2)["first.gain"] is not _controls(p1)["first.gain"]
    assert c1.name == "gain"  # registered control not renamed by the pipelines


def test_signature_default_overrides_control_default_and_is_validated():
    @interactive()
    def moved(img, gain: Annotated[float, Control(1.0, [0.0, 3.0])] = 2.5):
        return img

    assert Control.get_controls(moved)["gain"].value_default == 2.5
    with pytest.raises(ValueError, match="outside'.*parameter 'gain'.*does not fit"):

        @interactive()
        def outside(img, gain: Annotated[float, Control(1.0, [0.0, 3.0])] = 5.0):
            return img


# --- precedence ------------------------------------------------------------------


def test_decorator_wins_over_annotation():
    @interactive(gain=(2.0, [0.0, 10.0]))
    def both(img, gain: Annotated[float, (0.0, 3.0)] = 1.0):
        return img * gain

    ctrl = Control.get_controls(both)["gain"]
    assert ctrl.value_range == [0.0, 10.0] and ctrl.value_default == 2.0


def test_annotation_and_decorator_mixed():
    @interactive(flip=True)
    def mixed(img, gain: Annotated[float, (0.0, 3.0)] = 1.0, flip=True):
        return img * gain

    assert set(Control.get_controls(mixed)) == {"gain", "flip"}


def test_bare_decorator_without_parentheses():
    @interactive
    def bare(img, gain: Annotated[float, (0.0, 3.0)] = 1.0):
        return img * gain

    assert set(Control.get_controls(bare)) == {"gain"}
    assert bare(IMG)[0, 0] == 1.0
    p = _build(bare)
    assert p(IMG, gain=2.0)[0][0, 0] == 2.0
    assert hasattr(bare, "snapshot")


def test_bare_decorator_on_plain_function_keeps_working():
    @interactive
    def untyped(img, gain=1.0):
        return img * gain

    assert untyped(IMG, gain=3.0)[0, 0] == 3.0
    assert untyped.__interactive_pipe_inplace__ is False


# --- defaults --------------------------------------------------------------------


def test_parameters_without_default_stay_inputs():
    # an Enum / Literal / Annotated hint on a parameter without default is an
    # input (it may come from an upstream filter), never a control
    seen = []

    @interactive()
    def make_mode(img):
        return Style.GLOSSY

    @interactive()
    def apply_mode(img, style: Style, frame: Annotated[np.ndarray, (480, 640, 3)], gain: float = 1.0):
        seen.append(style)
        return img * style.value

    assert Control.get_controls(apply_mode) == {}

    def pipe(img):
        style = make_mode(img)
        out = apply_mode(img, style, img)
        return out

    assert HeadlessPipeline.from_function(pipe)(IMG)[0][0, 0] == 2
    assert seen[-1] is Style.GLOSSY


def test_signature_declaration_wins_over_hint():
    @interactive()
    def declared(
        img,
        mode: Literal["a", "b"] = ("a", ["a", "b"]),
        style: Style = Control("FLAT", ["FLAT", "GLOSSY"]),
        gain: Annotated[float, (0.0, 1.0)] = (2.0, [0.0, 5.0]),
    ):
        return img

    controls = Control.get_controls(declared)
    assert controls["mode"].value_range == ["a", "b"]
    assert not isinstance(controls["style"], MappedChoiceControl)
    assert controls["gain"].value_range == [0.0, 5.0]


# --- errors at decoration -------------------------------------------------------


@pytest.mark.parametrize(
    "annotation, default, exc, match",
    [
        (Annotated[float, (0.0, 3.0)], 5.0, ValueError, "the default 5.0 is outside the range \\[0.0, 3.0\\]"),
        (Annotated[int, (0, 3)], 1.5, TypeError, "not an int"),
        (Annotated[float, (0.0, 3.0)], "a", TypeError, "not a float"),
        (Annotated[float, (0.0, 3.0)], True, TypeError, "not a float"),
        (Annotated[bool, "Flip"], 1, TypeError, "not a bool"),
        (Annotated[float, (3.0, 0.0)], 1.0, ValueError, "must satisfy min <= max"),
        (Annotated[float, (0.0, 1.0, 5.0)], 0.5, ValueError, "larger than the range"),
        (Annotated[float, (0.0, 1.0, -0.1)], 0.5, ValueError, "step -0.1 must be > 0"),
        (Annotated[float, (0.0,)], 0.5, ValueError, "is not a range"),
        (Annotated[float, (0.0, 1.0, 0.5, 1.0)], 0.5, ValueError, "is not a range"),
        (Annotated[int, (0.5, 3)], 1, ValueError, "not made of ints"),
        (Annotated[bool, (0, 1)], False, ValueError, "checkbox takes no range"),
        (Literal["a", "b"], "c", ValueError, "not one of the choices"),
        (Annotated[Literal["a", "b"], ["a", "b"]], "a", ValueError, "already lists the choices"),
        (Style, "FLAT", ValueError, "not one of the choices"),
        (Annotated[str, ["a", "b"]], "c", ValueError, "not one of the choices"),
        (Annotated[str, []], "c", ValueError, "empty"),
        (Annotated[float, (0.0, 1.0), (0.0, 2.0)], 0.5, ValueError, "several ranges"),
        (Annotated[float, Control(1.0, [0, 2]), Control(1.0, [0, 2])], 1.0, ValueError, "several Control"),
        (Annotated[float, (0.0, 1.0), "a", "b", "c"], 0.5, ValueError, "too many labels"),
    ],
)
def test_invalid_annotations_raise_with_function_and_parameter(annotation, default, exc, match):
    def broken(img, param=default):
        return img

    broken.__annotations__ = {"param": annotation}
    with pytest.raises(exc, match=match) as info:
        interactive()(broken)
    message = str(info.value)
    assert "'test_invalid_annotations_raise_with_function_and_parameter.<locals>.broken'" in message
    assert "parameter 'param'" in message
    assert "Fix:" in message


def test_duplicate_label_in_one_filter_raises():
    with pytest.raises(ValueError, match="label 'Gain' is already used"):

        @interactive()
        def dup(img, a: Annotated[float, (0.0, 1.0), "Gain"] = 0.5, b: Annotated[float, (0.0, 1.0), "Gain"] = 0.5):
            return img


# --- Enum / non-string Literal values ---------------------------------------------


def test_enum_member_reaches_the_filter_through_every_path():
    seen = []

    @interactive()
    def styled(img, style: Style = Style.FLAT, color: Color = Color.GREEN):
        seen.append((style, color))
        return img * style.value

    p = _build(styled)
    p(IMG)
    assert seen[-1] == (Style.FLAT, Color.GREEN)
    p(IMG, style=Style.GLOSSY)  # member
    assert seen[-1][0] is Style.GLOSSY
    p(IMG, style="FLAT", color=Color.RED)  # label / str-enum member
    assert seen[-1] == (Style.FLAT, Color.RED)
    assert _controls(p)["color"].value == "RED"
    styled(IMG, style=Style.GLOSSY)
    assert seen[-1][0] is Style.GLOSSY
    with pytest.raises(ValueError, match="is not one of the choices"):
        p(IMG, style="SHINY")


def test_enum_literal_kwarg_in_pipeline_body():
    seen = []

    @interactive()
    def styled(img, style: Style = Style.FLAT):
        seen.append(style)
        return img

    def pipe(img):
        out = styled(img, style="GLOSSY")
        return out

    HeadlessPipeline.from_function(pipe)(IMG)
    assert seen[-1] is Style.GLOSSY


def test_non_string_literal_choices():
    seen = []

    @interactive()
    def sized(img, k: Literal[3, 5, 7] = 5):
        seen.append(k)
        return img

    ctrl = Control.get_controls(sized)["k"]
    assert ctrl.value_range == ["3", "5", "7"] and ctrl.value_default == "5"
    p = _build(sized)
    p(IMG)
    assert seen[-1] == 5 and isinstance(seen[-1], int)
    p(IMG, k=7)
    assert seen[-1] == 7
    p(IMG, k="3")
    assert seen[-1] == 3


def test_enum_describe_and_sweep(tmp_path):
    @interactive()
    def styled(img, style: Style = Style.FLAT):
        return img * style.value / 2

    p = _build(styled)
    entry = p.describe()["controls"][0]
    assert entry["kind"] == "dropdown" and entry["choices"] == ["FLAT", "GLOSSY"]
    p.sweep(tmp_path / "sweep.png", IMG, steps={"style": 2})
    assert (tmp_path / "sweep.png").exists()
    assert styled.describe()["controls"][0]["choices"] == ["FLAT", "GLOSSY"]


def test_tuning_round_trip_keeps_enum_labels(tmp_path):
    @interactive()
    def styled(img, style: Style = Style.FLAT):
        return img * style.value

    p = _build(styled)
    p(IMG, style=Style.GLOSSY)
    path = tmp_path / "tuning.yaml"
    p.export_tuning(path)
    p2 = _build(styled)
    p2.load_tuning(path)
    assert p2(IMG)[0][0, 0] == 2


# --- direct calls ----------------------------------------------------------------


def test_direct_call_uses_live_control_values():
    @interactive()
    def amp(img, gain: Annotated[float, (0.0, 3.0)] = 1.0):
        return img * gain

    Control.get_controls(amp)["gain"].value = 2.0
    try:
        assert amp(IMG)[0, 0] == 2.0
        assert amp(IMG, gain=0.5)[0, 0] == 0.5
    finally:
        Control.get_controls(amp)["gain"].reset()


def test_pipeline_runs_with_annotation_controls_in_every_cache_mode():
    @interactive()
    def amp(img, gain: Annotated[float, (0.0, 3.0)] = 1.0):
        return img * gain

    def pipe(img):
        out = amp(img)
        return out

    for cache in (False, True, "graph"):
        p = HeadlessPipeline.from_function(pipe, cache=cache)
        assert p(IMG, gain=1.0)[0][0, 0] == 1.0
        assert p(IMG, gain=3.0)[0][0, 0] == 3.0
        assert p(IMG)[0][0, 0] == 3.0


# --- string annotations -------------------------------------------------------------

FUTURE_SOURCE = """
from __future__ import annotations
import enum
from typing import Annotated, Literal
from interactive_pipe import interactive


class Mode(enum.Enum):
    A = 1
    B = 2


@interactive()
def typed(img, gain: Annotated[float, (0.0, 3.0)] = 1.0, mode: Mode = Mode.B, kind: Literal["x", "y"] = "y"):
    return img * gain


def make_local():
    LocalGain = Annotated[float, (0.0, 5.0)]

    @interactive()
    def local(img, gain: LocalGain = 4.0):
        return img * gain

    return local


@interactive()
def unresolvable(img, gain: Annotated[float, (0.0, 3.0)] = 1.0, other: DoesNotExist = 1):
    return img * gain


@interactive()
def unresolvable_control(img, gain: Annotated[float, Missing(0.0, 3.0)] = 1.0):
    return img * gain
"""


def test_future_annotations(tmp_path, monkeypatch, caplog):
    module_path = tmp_path / "future_filters.py"
    module_path.write_text(FUTURE_SOURCE)
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib

    module = importlib.import_module("future_filters")
    controls = Control.get_controls(module.typed)
    assert set(controls) == {"gain", "mode", "kind"}
    assert controls["mode"].value_default == "B"
    local = module.make_local()
    assert Control.get_controls(local)["gain"].value_range == [0.0, 5.0]
    # one unresolvable hint does not hide the resolvable ones
    assert set(Control.get_controls(module.unresolvable)) == {"gain"}
    # an unresolvable control declaration warns and makes no widget
    assert Control.get_controls(module.unresolvable_control) == {}
    assert "cannot resolve the annotation of 'gain'" in caplog.text


# --- GUI backend: the Enum dropdown is a plain string dropdown ----------------------


def test_qt_dropdown_drives_enum_parameter():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt_control = pytest.importorskip("interactive_pipe.graphical.qt_control")
    if not qt_control.PYQT_AVAILABLE:
        pytest.skip("no Qt binding")
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    seen = []

    @interactive()
    def styled(img, style: Style = Style.FLAT):
        seen.append(style)
        return img * style.value

    def pipe(img):
        out = styled(img)
        return out

    gui = qt_gui.InteractivePipeQT(pipeline=HeadlessPipeline.from_function(pipe))
    try:
        gui.pipeline.inputs = [IMG]
        widget = gui.window.widget_list["style"]
        assert [widget.control_widget.itemText(i) for i in range(2)] == ["FLAT", "GLOSSY"]
        widget.control_widget.setCurrentIndex(1)
        assert gui.pipeline.controls[0].value == "GLOSSY"
        gui.pipeline.run()
        assert seen[-1] is Style.GLOSSY
    finally:
        gui.close()


def test_filter_from_function_reads_annotations():
    from interactive_pipe.helper.filter_decorator import filter_from_function

    seen = []

    def styled(img, style: Style = Style.FLAT, gain: Annotated[float, (0.0, 2.0)] = 1.0):
        seen.append(style)
        return img * gain

    filt = filter_from_function(styled)
    assert set(filt.controls) == {"style", "gain"}
    filt.controls["style"].value = Style.GLOSSY
    filt(IMG)
    assert seen[-1] is Style.GLOSSY
    filt.values = {"style": "FLAT"}
    filt.run(IMG)
    assert seen[-1] is Style.FLAT


def test_none_default_makes_no_widget(caplog):
    from typing import Optional

    @interactive()
    def auto(
        img,
        mode: Literal["a", "b"] = None,
        style: Style = None,
        gain: Annotated[float, (0.0, 1.0)] = None,
        other: Optional[Literal["a", "b"]] = "a",
    ):
        return img

    assert Control.get_controls(auto) == {}
    assert "parameter 'gain': the default None makes no widget" in caplog.text
    assert "parameter 'mode'" not in caplog.text  # bare Literal: silent
    assert auto(IMG)[0, 0] == 1.0


def test_enum_and_literal_overrides_do_not_warn_about_clamping(tmp_path):
    import warnings

    @interactive()
    def styled(img, style: Style = Style.FLAT, k: Literal[3, 5] = 3):
        return img * style.value * k / 10

    p = _build(styled)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p.snapshot(tmp_path / "s.png", IMG, style=Style.GLOSSY, k=5)
        p.sweep(tmp_path / "w.png", IMG, style=[Style.FLAT, Style.GLOSSY])
