"""PointControl / RegionControl: values, validation, pixels, headless use, describe, tuning files."""

import json
import logging
from typing import Annotated, Tuple

import numpy as np
import pytest

from interactive_pipe import PointControl, RegionControl, interactive, to_pixels
from interactive_pipe.data_objects.parameters import YAML_SUPPORT
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.headless.pointer import PointerAxisControl, check_targets, to_fractions

IMAGE = np.zeros((40, 80, 3))


@interactive(seed=PointControl((0.5, 0.5), on="img", name="seed"))
def mark_seed(img, seed=(0.5, 0.5)):
    col, row = to_pixels(seed, img)
    out = img.copy()
    out[row, col] = 1.0
    return out


@interactive(roi=RegionControl((0.25, 0.25, 0.75, 0.75), name="roi"))
def crop_roi(img, roi=(0.25, 0.25, 0.75, 0.75)):
    x0, y0, x1, y1 = to_pixels(roi, img)
    return img[y0:y1, x0:x1]


def pointer_pipeline(img):
    marked = mark_seed(img)
    crop = crop_roi(img)
    return [marked, crop]


def _pipe():
    pipe = HeadlessPipeline.from_function(pointer_pipeline, inputs=["img"])
    for ctrl in pipe.controls:  # the registered controls are shared between tests
        ctrl.update(ctrl.value_default)
    pipe.inputs = [IMAGE]
    return pipe


# --- values and validation ---


def test_point_default_and_value():
    ctrl = PointControl((0.25, 1))
    assert ctrl.value == (0.25, 1.0)
    assert ctrl.value_default == (0.25, 1.0)
    assert ctrl.on is None
    ctrl.value = [0.1, 0.2]  # json tuning files give lists
    assert ctrl.value == (0.1, 0.2)
    ctrl.value = np.array([0.3, 0.4])
    assert ctrl.value == (0.3, 0.4)
    ctrl.value = "0.5, 0.6"
    assert ctrl.value == (0.5, 0.6)
    ctrl.reset()
    assert ctrl.value == (0.25, 1.0)


@pytest.mark.parametrize(
    "value, error, match",
    [
        ((0.5,), ValueError, "must have 2 elements"),
        ((0.1, 0.2, 0.3), ValueError, "must have 2 elements"),
        ((1.5, 0.2), ValueError, r"x=1.5 is outside \[0, 1\]"),
        ((0.5, -0.1), ValueError, "outside"),
        ((float("nan"), 0.5), ValueError, "outside"),
        (0.5, TypeError, "fractions of the image size"),
        (("a", 0.5), TypeError, "x must be a number"),
        ((True, 0.5), TypeError, "x must be a number"),
    ],
)
def test_point_invalid_values(value, error, match):
    with pytest.raises(error, match=match):
        PointControl(value)
    ctrl = PointControl((0.5, 0.5), name="probe")
    with pytest.raises(error, match=match):
        ctrl.value = value
    assert ctrl.value == (0.5, 0.5)


def test_float_noise_is_snapped():
    ctrl = PointControl((1.0000000001, -1e-12))
    assert ctrl.value == (1.0, 0.0)


def test_region_reordered():
    ctrl = RegionControl((0.75, 0.8, 0.25, 0.2))
    assert ctrl.value == (0.25, 0.2, 0.75, 0.8)
    ctrl.value = (0.9, 0.1, 0.1, 0.9)
    assert ctrl.value == (0.1, 0.1, 0.9, 0.9)


def test_region_invalid():
    with pytest.raises(ValueError, match="must have 4 elements"):
        RegionControl((0.1, 0.2))
    with pytest.raises(ValueError, match=r"y1=2 is outside"):
        RegionControl((0.1, 0.2, 0.3, 2))


def test_on_must_be_a_name():
    with pytest.raises(TypeError, match="on= must be the name"):
        PointControl((0.5, 0.5), on=3)  # type: ignore[arg-type]


# --- pixels ---


def test_to_pixels_point():
    assert to_pixels((0.0, 0.0), IMAGE) == (0, 0)
    assert to_pixels((1.0, 1.0), IMAGE) == (79, 39)  # clipped into the image
    assert to_pixels((0.5, 0.5), IMAGE) == (40, 20)
    assert to_pixels((0.5, 0.5), (40, 80)) == (40, 20)  # a shape works too


def test_to_pixels_region_never_empty():
    assert to_pixels((0.25, 0.25, 0.75, 0.75), IMAGE) == (20, 10, 60, 30)
    x0, y0, x1, y1 = to_pixels((0.5, 0.5, 0.5, 0.5), IMAGE)
    assert IMAGE[y0:y1, x0:x1].shape[:2] == (1, 1)
    x0, y0, x1, y1 = to_pixels((1.0, 1.0, 1.0, 1.0), IMAGE)
    assert IMAGE[y0:y1, x0:x1].shape[:2] == (1, 1)
    assert to_pixels((0.0, 0.0, 1.0, 1.0), IMAGE) == (0, 0, 80, 40)


def test_to_pixels_errors():
    with pytest.raises(TypeError, match="needs an image"):
        to_pixels((0.5, 0.5), np.zeros(5))
    with pytest.raises(ValueError, match="outside"):
        to_pixels((2.0, 0.5), IMAGE)


def test_to_fractions_round_trip():
    assert to_pixels(to_fractions((13, 7), IMAGE), IMAGE) == (13, 7)
    assert to_pixels(to_fractions((10, 5, 30, 25), IMAGE), IMAGE) == (10, 5, 30, 25)


# --- headless pipeline ---


def test_pipeline_parameter_and_default():
    pipe = _pipe()
    marked, crop = pipe.run()
    assert np.argwhere(marked[..., 0]).tolist() == [[20, 40]]
    assert crop.shape == (20, 40, 3)
    marked, _ = pipe(IMAGE, seed=(0.1, 0.2))
    assert np.argwhere(marked[..., 0]).tolist() == [[8, 8]]
    _, crop = pipe(IMAGE, roi=(0.0, 0.0, 0.5, 1.0))
    assert crop.shape == (40, 40, 3)


def test_pipeline_rejects_invalid_value():
    pipe = _pipe()
    with pytest.raises(ValueError, match="outside"):
        pipe(IMAGE, seed=(1.5, 0.2))


def test_sweep_over_points(tmp_path):
    pipe = _pipe()
    path = tmp_path / "sweep.png"
    pipe.sweep(path, IMAGE, seed=[(0.1, 0.1), (0.6, 0.4)])
    assert path.exists()


def test_tuning_round_trip(tmp_path):
    pipe = _pipe()
    pipe(IMAGE, seed=(0.1, 0.2), roi=(0.6, 0.5, 0.2, 0.1))
    path = tmp_path / "tuning.json"
    pipe.export_tuning(path)
    saved = json.loads(path.read_text())
    assert saved["mark_seed"]["seed"] == [0.1, 0.2]
    assert saved["crop_roi"]["roi"] == [0.2, 0.1, 0.6, 0.5]
    other = _pipe()
    other.import_tuning(path)
    values = {ctrl.name: ctrl.value for ctrl in other.controls}
    assert values == {"seed": (0.1, 0.2), "roi": (0.2, 0.1, 0.6, 0.5)}
    marked, crop = other.run()
    assert np.argwhere(marked[..., 0]).tolist() == [[8, 8]]
    assert crop.shape == (16, 32, 3)


@pytest.mark.skipif(not YAML_SUPPORT, reason="no yaml")
def test_tuning_round_trip_yaml(tmp_path):
    pipe = _pipe()
    pipe(IMAGE, seed=(0.1, 0.2))
    path = tmp_path / "tuning.yaml"
    pipe.export_tuning(path)
    other = _pipe()
    other.import_tuning(path)
    assert next(ctrl for ctrl in other.controls if ctrl.name == "seed").value == (0.1, 0.2)


def test_literal_keyword_in_pipeline_body():
    def literal_pipeline(img):
        marked = mark_seed(img, seed=(0.0, 0.0))
        return marked

    pipe = HeadlessPipeline.from_function(literal_pipeline, inputs=["img"])
    (marked,) = pipe(IMAGE)
    assert np.argwhere(marked[..., 0]).tolist() == [[0, 0]]


def test_annotation_form():
    @interactive()
    def probe(img, seed: Annotated[Tuple[float, float], PointControl((0.5, 0.5))] = (0.25, 0.75)):
        col, row = to_pixels(seed, img)
        return img[row]

    def annotated_pipeline(img):
        profile = probe(img)
        return profile

    pipe = HeadlessPipeline.from_function(annotated_pipeline, inputs=["img"])
    (ctrl,) = pipe.controls
    assert isinstance(ctrl, PointControl)
    assert ctrl.name == "seed"
    (profile,) = pipe(IMAGE, seed=(0.0, 0.5))
    assert profile.shape == (80, 3)


# --- describe / targets ---


def test_describe_kinds_and_target():
    pipe = _pipe()
    controls = {entry["name"]: entry for entry in pipe.describe()["controls"]}
    assert controls["seed"]["kind"] == "point"
    assert controls["seed"]["on"] == "img"
    assert controls["seed"]["axes"] == ["x", "y"]
    assert controls["seed"]["value"] == [0.5, 0.5]
    assert controls["roi"]["kind"] == "region"
    assert controls["roi"]["on"] is None
    json.dumps(pipe.describe())
    text = pipe.summary()
    assert "seed point(x, y in [0, 1]) = [0.5, 0.5] on 'img'" in text
    assert "on the first image" in text


def test_unknown_target_is_reported_with_the_available_names():
    @interactive(where=PointControl((0.5, 0.5), on="missing"))
    def misplaced(img, where=(0.5, 0.5)):
        return img

    def bad_pipeline(img):
        out = misplaced(img)
        return [img, out]

    pipe = HeadlessPipeline.from_function(bad_pipeline, inputs=["img"])
    with pytest.raises(ValueError, match=r"on='missing' is not an output .*Available outputs: \['img', 'out'\]"):
        check_targets(pipe)
    with pytest.raises(ValueError, match="on='missing'"):
        pipe.describe()


def test_target_may_be_any_produced_variable():
    pipe = _pipe()
    check_targets(pipe)  # 'img' is the input


# --- slider fallback ---


def test_point_fallback_sliders_edit_the_parent():
    pipe = _pipe()
    seed = next(ctrl for ctrl in pipe.controls if isinstance(ctrl, PointControl))
    x_slider, y_slider = seed.fallback_controls()
    assert seed.fallback_controls()[0] is x_slider  # built once
    assert isinstance(x_slider, PointerAxisControl)
    assert (x_slider.name, y_slider.name) == ("seed x", "seed y")
    assert (x_slider._type, x_slider.value_range) == (float, [0.0, 1.0])
    x_slider.update(0.1)
    assert seed.value == (0.1, 0.5)
    assert pipe.parameters["mark_seed"]["seed"] == (0.1, 0.5)
    seed.value = (0.3, 0.4)
    assert (x_slider.value, y_slider.value) == (0.3, 0.4)
    x_slider.value = x_slider.value_default  # what a backend reset does
    assert seed.value == (0.5, 0.4)


def test_region_fallback_sliders_keep_order(caplog):
    roi = RegionControl((0.25, 0.25, 0.75, 0.75), name="roi")
    x0, y0, x1, y1 = roi.fallback_controls()
    assert [s.name for s in (x0, y0, x1, y1)] == ["roi x0", "roi y0", "roi x1", "roi y1"]
    x0.value = 0.9  # past x1: x1 follows
    assert roi.value == (0.9, 0.25, 0.9, 0.75)
    y1.value = 0.1  # before y0: y0 follows
    assert roi.value == (0.9, 0.1, 0.9, 0.1)
    with caplog.at_level(logging.WARNING):
        x1.value = 1.5  # sliders clamp like any slider
    assert roi.value[2] == 1.0
