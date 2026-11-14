"""Gesture logic shared by the backends (graphical/pointer_input.py), without any GUI."""

import numpy as np
import pytest

from interactive_pipe import PointControl, RegionControl, interactive, to_pixels
from interactive_pipe.graphical.pointer_input import (
    Gesture,
    PointerTargets,
    controls_for_backend,
    handles,
    help_lines,
    overlay_items,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline

IMAGE = np.zeros((10, 20, 3))


def _targets(*controls, names=None, contents=None, styles=None):
    names = names or [["img", "other"]]
    contents = contents or [[IMAGE, IMAGE]]
    return PointerTargets(controls, names, contents, styles)


def test_default_target_is_the_first_image_output():
    point = PointControl((0.5, 0.5), name="p")
    targets = _targets(point, names=[["text", "img"]], contents=[["hello", IMAGE]])
    assert targets.cell_of(point) == (0, 1)


def test_named_target_and_non_image_targets():
    on_other = PointControl((0.5, 0.5), on="other", name="a")
    on_text = PointControl((0.5, 0.5), on="text", name="b")
    targets = _targets(on_other, on_text, names=[["img", "other", "text"]], contents=[[IMAGE, IMAGE, "txt"]])
    assert targets.cell_of(on_other) == (0, 1)
    assert targets.cell_of(on_text) is None  # a text cell takes no gesture
    assert targets.controls_at((0, 1)) == [on_other]


def test_data_size_of_a_heatmap_with_colorbar():
    heat = np.zeros((20, 30))
    point = PointControl((0.5, 0.5), name="p")
    targets = _targets(point, names=[["heat"]], contents=[[heat]], styles={(0, 0): {"colorbar": True}})
    width, height = targets.data_size((0, 0), (999, 999))[:2]  # the shown shape includes the colorbar
    assert width / 30 == height / 20 > 1
    plain = _targets(point, names=[["heat"]], contents=[[heat]])
    assert plain.data_size((0, 0), (20, 30)) == (30.0, 20.0)


def test_click_moves_the_nearest_point():
    left = PointControl((0.1, 0.5), name="left")
    right = PointControl((0.9, 0.5), name="right")
    targets = _targets(left, right)
    gesture = Gesture()
    assert gesture.press(targets, (0, 0), (0.7, 0.4), (100, 100), shift=False)
    assert gesture.release(targets, (0.7, 0.4), (101, 101)) is right
    assert right.value == (0.7, 0.4) and left.value == (0.1, 0.5)
    assert not gesture.active


def test_a_drag_is_not_a_click():
    point = PointControl((0.5, 0.5), name="p")
    targets = _targets(point)
    gesture = Gesture()
    gesture.press(targets, (0, 0), (0.2, 0.2), (100, 100), shift=False)
    assert gesture.move((0.3, 0.3), (110, 100)) is None
    assert gesture.release(targets, (0.3, 0.3), (110, 100)) is None
    assert point.value == (0.5, 0.5)


def test_press_is_refused_when_nothing_listens():
    region = RegionControl((0.1, 0.1, 0.2, 0.2), name="r")
    targets = _targets(region)
    gesture = Gesture()
    assert not gesture.press(targets, (0, 0), (0.5, 0.5), (0, 0), shift=False)  # no point here
    assert not gesture.press(targets, (0, 1), (0.5, 0.5), (0, 0), shift=True)  # not the target cell
    assert not gesture.press(targets, (0, 0), (1.5, 0.5), (0, 0), shift=True)  # outside the image
    point_only = _targets(PointControl((0.5, 0.5), name="p"))
    assert not gesture.press(point_only, (0, 0), (0.5, 0.5), (0, 0), shift=True)  # shift: no region


def test_region_drag_is_live_reordered_and_clamped():
    near = RegionControl((0.0, 0.0, 0.2, 0.2), name="near")
    far = RegionControl((0.7, 0.7, 0.9, 0.9), name="far")
    targets = _targets(near, far)
    gesture = Gesture()
    assert gesture.press(targets, (0, 0), (0.8, 0.8), (50, 50), shift=True)
    assert gesture.drawing_region
    assert gesture.move((0.81, 0.8), (51, 50)) is None  # within the click tolerance
    assert gesture.move((0.5, 0.6), (30, 40)) is far
    assert far.value == (0.5, 0.6, 0.8, 0.8)
    assert gesture.release(targets, (1.4, -0.2), (90, 0)) is far
    assert far.value == (0.8, 0.0, 1.0, 0.8)
    assert near.value == (0.0, 0.0, 0.2, 0.2)


def test_overlay_items_regions_first():
    point = PointControl((0.5, 0.25), name="p")
    region = RegionControl((0.0, 0.5, 0.5, 1.0), name="r")
    items = overlay_items(_targets(point, region), (0, 0), (20.0, 10.0))
    assert items == [("region", (0.0, 5.0, 10.0, 10.0), "r"), ("point", (10.0, 2.5), "p")]


def test_handles_and_help():
    point = PointControl((0.5, 0.5), name="p", on="img")
    region = RegionControl((0.1, 0.1, 0.2, 0.2), name="r")
    assert handles(True, region) and not handles(False, point)
    assert handles(("point",), point) and not handles(("point",), region)
    shown = controls_for_backend([point, region], ("point",))
    assert shown[0] is point and [ctrl.name for ctrl in shown[1:]] == ["r x0", "r y0", "r x1", "r y1"]
    assert help_lines(shown) == ["[click] on 'img' : set p"]


@interactive(rp_seed=PointControl((0.5, 0.5), name="rp_seed"))
def rp_mark(img, rp_seed=(0.5, 0.5)):
    col, row = to_pixels(rp_seed, img)
    out = img.copy()
    out[row, col] = 1.0
    return out


def repeated_pipeline(img):
    first = rp_mark(img)
    second = rp_mark(first)
    return [first, second]


def test_repeated_filter_gets_its_own_point_and_sliders():
    pipe = HeadlessPipeline.from_function(repeated_pipeline, inputs=["img"])
    first, second = pipe.controls
    assert (first.name, second.name) == ("rp_seed", "rp_seed_1")
    assert isinstance(second, PointControl)
    assert [s.name for s in second.fallback_controls()] == ["rp_seed_1 x", "rp_seed_1 y"]
    assert first.fallback_controls()[0].parent is first
    first.update(first.value_default)
    out_first, out_second = pipe(IMAGE, rp_seed_1=(0.0, 0.0))
    assert np.argwhere(out_first[..., 0]).tolist() == [[5, 10]]
    assert np.argwhere(out_second[..., 0]).tolist() == [[0, 0], [5, 10]]


def test_targets_ignore_a_pipeline_without_pointer_controls():
    assert _targets().controls == []
    with pytest.raises(TypeError):
        PointControl((0.5, 0.5), on=["img"])  # type: ignore[arg-type]
