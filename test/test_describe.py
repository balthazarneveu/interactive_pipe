"""HeadlessPipeline.describe / summary: the pipeline as plain data and text."""

import json

import numpy as np
import pytest

from interactive_pipe import (
    CircularControl,
    Control,
    KeyboardControl,
    Panel,
    RangeControl,
    TextPrompt,
    TimeControl,
    interactive,
    interactive_pipeline,
)
from interactive_pipe.headless.describe import to_plain

DESC_PANEL = Panel("Tone")


@interactive(
    gain=Control(1.0, [0.0, 2.0], tooltip="Multiply the image", group=DESC_PANEL),
    angle=CircularControl(0.0, [0.0, 360.0]),
    flip=Control(False),
    mode=Control("a", ["a", "b"]),
    window=RangeControl((0.2, 0.8), [0.0, 1.0]),
    label=TextPrompt("hello"),
    count=Control(3),
)
def desc_tone(img, gain=1.0, angle=0.0, flip=False, mode="a", window=(0.2, 0.8), label="hello", count=3):
    """Adjust the tone.

    Longer explanation that is not part of the summary.
    """
    return img * gain


@interactive(
    step=KeyboardControl(2, [0, 10], keydown="j", keyup="k", modulo=True),
    time=TimeControl(update_interval_ms=40),
)
def desc_keys(img, step=2, time=0.0, scale=np.float32(0.5)):
    return img, img * scale


def desc_pipeline(img):
    toned = desc_tone(img)
    keyed, scaled = desc_keys(toned)
    return [[toned, keyed], [scaled]]


@pytest.fixture
def pipe():
    return interactive_pipeline(gui=None)(desc_pipeline)


def by_name(data):
    return {entry["name"]: entry for entry in data["controls"]}


def test_describe_round_trips_through_json(pipe):
    data = pipe.describe()
    assert json.loads(json.dumps(data)) == data


def test_describe_structure(pipe):
    data = pipe.describe()
    assert data["name"] == "desc_pipeline"
    assert data["inputs"] == ["img"]
    assert data["outputs"] == [["toned", "keyed"], ["scaled"]]
    assert [filt["name"] for filt in data["filters"]] == ["desc_tone", "desc_keys"]
    tone, keys = data["filters"]
    assert tone["inputs"] == ["img"] and tone["outputs"] == ["toned"]
    assert keys["outputs"] == ["keyed", "scaled"]
    assert tone["doc"] == "Adjust the tone."
    assert tone["parameters"]["window"] == [0.2, 0.8]
    assert keys["parameters"]["scale"] == 0.5  # numpy scalar -> float
    assert isinstance(keys["parameters"]["scale"], float)
    assert "gain" in tone["controls"]


def test_control_kinds_and_fields(pipe):
    controls = by_name(pipe.describe())
    kinds = {name: entry["kind"] for name, entry in controls.items()}
    assert kinds == {
        "gain": "slider",
        "angle": "slider",
        "flip": "checkbox",
        "mode": "dropdown",
        "window": "range",
        "label": "text",
        "count": "number",
        "step": "keyboard",
        "time": "time",
    }
    gain = controls["gain"]
    assert gain["filter"] == "desc_tone" and gain["parameter"] == "gain"
    assert gain["range"] == [0.0, 2.0] and gain["step"] == pytest.approx(0.02)
    assert gain["default"] == 1.0 and gain["value"] == 1.0
    assert gain["group"] == "Tone"
    assert gain["tooltip"] == "Multiply the image"
    assert controls["angle"]["circular"] is True
    assert controls["mode"]["choices"] == ["a", "b"]
    assert controls["step"]["keys"] == {"keydown": "j", "keyup": "k", "modulo": True}
    assert controls["time"]["keys"] == {"pause_resume": "p"}
    assert controls["time"]["update_interval_ms"] == 40
    assert "keys" not in gain and "tooltip" not in controls["flip"]


def test_describe_reports_current_values(pipe):
    pipe(np.ones((4, 4)), gain=1.5)
    controls = by_name(pipe.describe())
    assert controls["gain"]["value"] == 1.5 and controls["gain"]["default"] == 1.0


def test_summary_text(pipe):
    text = pipe.summary()
    assert text.startswith("Pipeline 'desc_pipeline'")
    assert "desc_tone(img) -> toned" in text
    assert "outputs: [toned, keyed] / [scaled]" in text
    assert "gain" in text and "in [0, 2]" in text
    assert "keys keydown='j'" in text
    assert "# Multiply the image" in text


def test_to_plain():
    assert to_plain(np.int64(3)) == 3
    assert to_plain((np.float32(0.5), "a")) == [0.5, "a"]
    assert to_plain(Panel("P")) == "P"
    assert to_plain(np.zeros((2, 2))) == "array(2, 2) float64"
    assert to_plain({1: {2}}) == {"1": [2]}
