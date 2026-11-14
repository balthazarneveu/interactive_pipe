"""interactive_pipe.draw: pure drawing functions on numpy images."""

import numpy as np
import pytest

import interactive_pipe
from interactive_pipe import draw, interactive
from interactive_pipe.headless.pipeline import HeadlessPipeline

RED = (1.0, 0.0, 0.0)


def frozen(array: np.ndarray) -> np.ndarray:
    array = array.copy()
    array.setflags(write=False)  # pipeline inputs are read-only views
    return array


def float_image(h=40, w=60, value=0.25, channels=3):
    shape = (h, w) if channels is None else (h, w, channels)
    return frozen(np.full(shape, value, dtype=np.float64))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def test_draw_is_exported():
    assert interactive_pipe.draw is draw
    assert "draw" in interactive_pipe.__all__
    for name in ("points", "boxes", "lines", "polygon", "text", "mask"):
        assert callable(getattr(draw, name))


# ---------------------------------------------------------------------------
# Image conventions: pure, dtype / range / channels
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "img",
    [
        float_image(),
        frozen(np.full((40, 60, 3), 0.25, dtype=np.float32)),
        frozen(np.full((40, 60, 3), 64, dtype=np.uint8)),
        frozen(np.full((40, 60, 3), 16000, dtype=np.uint16)),
    ],
    ids=["float64", "float32", "uint8", "uint16"],
)
def test_dtype_range_kept_and_input_untouched(img):
    before = img.copy()
    out = draw.boxes(img, [5, 5, 30, 20], color="red")
    assert out.dtype == img.dtype and out.shape == img.shape
    np.testing.assert_array_equal(img, before)
    full = {np.uint8: 255, np.uint16: 65535}.get(img.dtype.type, 1.0)
    np.testing.assert_allclose(out[5, 10], [full, 0, 0])  # on the top edge
    np.testing.assert_array_equal(out[12, 15], img[12, 15])  # inside: untouched


def test_unmarked_float_pixels_keep_their_exact_values():
    img = frozen(np.random.default_rng(0).random((30, 30, 3)))
    out = draw.points(img, (10, 10), radius=2, color="white")
    changed = (out != img).any(axis=-1)
    assert 0 < changed.sum() < 30
    np.testing.assert_array_equal(out[~changed], img[~changed])


@pytest.mark.parametrize("shape", [(20, 30), (20, 30, 1)])
def test_grayscale_is_promoted_to_rgb(shape):
    img = frozen(np.full(shape, 0.5))
    out = draw.points(img, (4, 4), color="red", radius=1)
    assert out.shape == (20, 30, 3)
    np.testing.assert_allclose(out[4, 4], RED)
    np.testing.assert_allclose(out[10, 10], [0.5, 0.5, 0.5])


def test_uint8_grayscale_is_promoted_to_rgb():
    out = draw.points(frozen(np.full((20, 30), 100, dtype=np.uint8)), (4, 4), color="red", radius=1)
    assert out.shape == (20, 30, 3) and out.dtype == np.uint8
    np.testing.assert_array_equal(out[4, 4], [255, 0, 0])
    np.testing.assert_array_equal(out[10, 10], [100, 100, 100])


def test_rgba_keeps_four_channels_and_marks_become_opaque():
    img = frozen(np.zeros((20, 30, 4)))
    out = draw.points(img, (4, 4), color="red", radius=1)
    assert out.shape == (20, 30, 4)
    np.testing.assert_allclose(out[4, 4], [1, 0, 0, 1])
    np.testing.assert_allclose(out[10, 10], [0, 0, 0, 0])


def test_unsupported_images_raise():
    with pytest.raises(TypeError):
        draw.points([[0.0]], (0, 0))
    with pytest.raises(TypeError):
        draw.points(np.zeros((4, 4), dtype=np.int32), (0, 0))
    with pytest.raises(ValueError):
        draw.points(np.zeros((4, 4, 2)), (0, 0))


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------
def test_xy_order_is_column_then_row():
    out = draw.points(float_image(), (50, 3), color="red", radius=0.5)
    np.testing.assert_allclose(out[3, 50], RED)
    assert not np.allclose(out[50 % 40, 3], RED)


def test_sub_pixel_and_out_of_image_marks_are_accepted():
    img = float_image()
    out = draw.points(img, [(10.4, 10.6), (-50, -50), (1e9, 5), (np.nan, 3)], color="red", radius=2)
    assert np.allclose(out[11, 10], RED)
    boxes = draw.boxes(img, [[-100, -100, 1000, 1000], [55, 35, 80, 90]], color="red")
    np.testing.assert_allclose(boxes[38, 55], RED)  # partly visible box: its left edge
    lines = draw.lines(img, [[-1000, 20], [1000, 20]], color="red")
    np.testing.assert_allclose(lines[20, 0], RED)
    np.testing.assert_allclose(lines[20, 59], RED)


def test_empty_inputs_return_a_copy():
    img = float_image()
    for out in (draw.points(img, np.zeros((0, 2))), draw.boxes(img, []), draw.lines(img, [])):
        np.testing.assert_array_equal(out, img)
        assert out is not img


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "color, expected",
    [
        ("red", RED),
        ("#00ff00", (0.0, 1.0, 0.0)),
        ((0.0, 0.0, 1.0), (0.0, 0.0, 1.0)),
        ((255, 128, 0), (1.0, 128 / 255, 0.0)),
        ("tab:blue", draw.DEFAULT_COLORS[0]),
    ],
)
def test_colour_formats(color, expected):
    np.testing.assert_allclose(draw.to_rgb(color), expected, atol=2e-3)


def test_bad_colours_raise():
    with pytest.raises(ValueError):
        draw.to_rgb("not-a-colour")
    with pytest.raises(ValueError):
        draw.to_rgb((1.0, 0.0))


def test_default_cycle_and_per_item_colours():
    img = float_image(channels=3)
    pts = [(5, 5), (15, 5), (25, 5)]
    cycled = draw.points(img, pts, radius=0.5)
    for k, (x, y) in enumerate(pts):
        np.testing.assert_allclose(cycled[y, x], draw.DEFAULT_COLORS[k], atol=3e-3)
    listed = draw.points(img, pts, radius=0.5, color=["red", "blue"])
    np.testing.assert_allclose(listed[5, 5], RED)
    np.testing.assert_allclose(listed[5, 15], (0, 0, 1))
    np.testing.assert_allclose(listed[5, 25], RED)  # cycled


# ---------------------------------------------------------------------------
# Each function
# ---------------------------------------------------------------------------
def test_boxes_xywh_equals_xyxy_and_corner_order_does_not_matter():
    img = float_image()
    xyxy = draw.boxes(img, [[5, 6, 25, 30]], color="red")
    xywh = draw.boxes(img, [[5, 6, 20, 24]], color="red", fmt="xywh")
    swapped = draw.boxes(img, [[25, 30, 5, 6]], color="red")
    np.testing.assert_array_equal(xyxy, xywh)
    np.testing.assert_array_equal(xyxy, swapped)
    with pytest.raises(ValueError):
        draw.boxes(img, [[0, 0, 1, 1]], fmt="cxcywh")
    with pytest.raises(ValueError):
        draw.boxes(img, [[0, 0, 1]])


def test_box_labels_are_drawn_and_counted():
    img = float_image(h=80, w=120)
    plain = draw.boxes(img, [[10, 40, 60, 70]], color="red")
    labelled = draw.boxes(img, [[10, 40, 60, 70]], color="red", labels=["cat"])
    assert (labelled != plain).any(axis=-1)[:40].sum() > 50  # tag above the box
    at_top = draw.boxes(img, [[10, -5, 60, 70]], color="red", labels=["cat"])
    assert (at_top != draw.boxes(img, [[10, -5, 60, 70]], color="red")).any()  # inside, still visible
    with pytest.raises(ValueError):
        draw.boxes(img, [[0, 0, 5, 5]], labels=["a", "b"])


def test_point_labels_and_outline_circles():
    img = float_image(h=60, w=100)
    out = draw.points(img, (20, 30), radius=5, filled=False, color="red", labels=["p1"])
    np.testing.assert_allclose(out[30, 15], RED)  # left of the circle
    np.testing.assert_allclose(out[30, 20], img[30, 20])  # hollow centre
    assert (out[:, 27:] != img[:, 27:]).any()  # label on the right


def test_lines_polyline_segments_and_ragged_list():
    img = float_image()
    polyline = draw.lines(img, [[0, 0], [10, 0], [10, 10]], color="red", width=1)
    np.testing.assert_allclose(polyline[0, 5], RED)
    np.testing.assert_allclose(polyline[5, 10], RED)
    segments = draw.lines(img, np.array([[[0, 20], [20, 20]], [[30, 0], [30, 10]]]), color="red", width=1)
    np.testing.assert_allclose(segments[20, 10], RED)
    np.testing.assert_allclose(segments[5, 30], RED)
    assert not np.allclose(segments[20, 25], RED)  # segments are not joined
    ragged = draw.lines(img, [np.array([[0, 30], [5, 30]]), np.array([[40, 0], [40, 5], [45, 5]])], width=1)
    assert (ragged != img).any(axis=-1).sum() > 10
    closed = draw.lines(img, [[5, 5], [15, 5], [15, 15]], color="red", width=1, closed=True)
    np.testing.assert_allclose(closed[10, 10], RED)  # the closing diagonal


def test_polygon_outline_and_translucent_fill():
    img = float_image(value=0.0)
    square = [[10, 10], [30, 10], [30, 30], [10, 30]]
    outline = draw.polygon(img, square, color="red", width=1)
    np.testing.assert_allclose(outline[10, 20], RED)
    np.testing.assert_allclose(outline[20, 20], [0, 0, 0])
    filled = draw.polygon(img, square, color="red", width=0, fill_alpha=0.5)
    np.testing.assert_allclose(filled[20, 20], [0.5, 0, 0], atol=3e-3)
    with pytest.raises(ValueError):
        draw.polygon(img, square, fill_alpha=2.0)


def test_text_default_is_readable_on_dark_and_bright():
    for value in (0.0, 1.0):
        img = float_image(h=60, w=120, value=value)
        out = draw.text(img, "Hello", (10, 10), size=16)
        region = out[5:35, 5:80]
        # white letters with a black outline: both extremes present on any background
        assert (region.min(axis=-1) > 0.9).sum() > 20
        assert (region.max(axis=-1) < 0.1).sum() > 20


def test_text_anchor_background_and_multiline():
    img = float_image(h=80, w=160, value=0.5)
    top_left = draw.text(img, "Hi", (80, 40), anchor="top-left")
    bottom_right = draw.text(img, "Hi", (80, 40), anchor="bottom-right")
    assert (top_left != img).any(axis=-1)[41:, 81:].any()
    assert not (top_left != img).any(axis=-1)[:38, :78].any()
    assert (bottom_right != img).any(axis=-1)[:40, :80].any()
    assert not (bottom_right != img).any(axis=-1)[42:, 82:].any()
    boxed = draw.text(img, "line 1\nline 2", (5, 5), background="black", background_alpha=1.0, outline=None)
    box_pixels = (boxed[:40, :60] == 0.0).all(axis=-1).sum()
    assert box_pixels > 200  # opaque black box behind the two lines
    several = draw.text(img, ["a", "b"], [(10, 10), (100, 50)], color=["red", "blue"])
    assert (several != img).any(axis=-1)[:30, :40].any() and (several != img).any(axis=-1)[40:, 90:].any()
    with pytest.raises(ValueError):
        draw.text(img, "x", (0, 0), anchor="middle-ish")
    with pytest.raises(ValueError):
        draw.text(img, ["a", "b"], (0, 0))


def test_mask_boolean_label_and_soft():
    img = float_image(h=10, w=10, value=0.0)
    boolean = np.zeros((10, 10), bool)
    boolean[2:4, 2:4] = True
    out = draw.mask(img, boolean, color="red", alpha=0.5)
    np.testing.assert_allclose(out[2, 2], [0.5, 0, 0])
    np.testing.assert_allclose(out[5, 5], [0, 0, 0])

    labels = np.zeros((10, 10), int)
    labels[0, 0], labels[0, 1], labels[0, 2] = 1, 2, 11
    out = draw.mask(img, labels, alpha=1.0)
    np.testing.assert_allclose(out[0, 0], draw.DEFAULT_COLORS[0])
    np.testing.assert_allclose(out[0, 1], draw.DEFAULT_COLORS[1])
    np.testing.assert_allclose(out[0, 2], draw.DEFAULT_COLORS[0])  # 11 -> cycled
    np.testing.assert_allclose(out[5, 5], [0, 0, 0])
    one_colour = draw.mask(img, labels, color="red", alpha=1.0)
    np.testing.assert_allclose(one_colour[0, 1], RED)

    soft = np.zeros((10, 10))
    soft[1, 1] = 0.5
    out = draw.mask(img, soft, color="red", alpha=1.0)
    np.testing.assert_allclose(out[1, 1], [0.5, 0, 0])

    with pytest.raises(ValueError):
        draw.mask(img, np.zeros((5, 5), bool))
    with pytest.raises(ValueError):
        draw.mask(img, boolean, alpha=1.5)


def test_mask_uint8_rounding():
    img = frozen(np.zeros((4, 4, 3), dtype=np.uint8))
    out = draw.mask(img, np.ones((4, 4), bool), color=(1.0, 1.0, 1.0), alpha=0.5)
    assert out.dtype == np.uint8
    np.testing.assert_array_equal(out[0, 0], [128, 128, 128])


# ---------------------------------------------------------------------------
# In a pipeline
# ---------------------------------------------------------------------------
@interactive(threshold=(0.5, [0.0, 1.0]))
def detect_and_draw(img, threshold=0.5):
    ys, xs = np.nonzero(img[..., 0] > threshold)
    boxes = [[xs.min(), ys.min(), xs.max(), ys.max()]] if xs.size else []
    return draw.boxes(img, boxes, labels=["blob"] * len(boxes), color="red")


def drawing_pipeline(img):
    out = detect_and_draw(img)
    return out


def test_drawing_inside_a_pipeline_on_a_read_only_input():
    img = np.zeros((40, 40, 3))
    img[10:20, 15:30] = 0.9
    pipe = HeadlessPipeline.from_function(drawing_pipeline)
    out = pipe(frozen(img))[0]
    np.testing.assert_allclose(out[10, 20], RED)
    rendered = pipe.snapshot(None)
    assert rendered.ndim == 3


def test_translucent_fill_on_uint8_direct_path():
    img = frozen(np.zeros((40, 40, 3), dtype=np.uint8))
    out = draw.polygon(img, [[5, 5], [30, 5], [30, 30], [5, 30]], color="red", width=0, fill_alpha=0.5)
    assert out.dtype == np.uint8
    np.testing.assert_allclose(out[20, 20], [128, 0, 0], atol=1)
    np.testing.assert_array_equal(out[35, 35], [0, 0, 0])
