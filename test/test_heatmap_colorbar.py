"""Heatmap display options: colorbar drawn into the image, diverging range
(center), NaN / masked / inf policy and the Qt pixel readout of the scalar."""

import os

import matplotlib
import numpy as np
import pytest

from interactive_pipe import FilterError, interactive, layout
from interactive_pipe.graphical.display import (
    BAD_COLOR,
    COLORBAR_MIN_HEIGHT,
    apply_display_style,
    colorbar_header,
    colorbar_scale,
    colorbar_strip,
    colorbar_upscale,
    heatmap_geometry,
    place_colorbar_labels,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline

RAMP = np.tile(np.linspace(-1.0, 3.0, 32), (32, 1))


# ---------------------------------------------------------------------------
# Colorbar
# ---------------------------------------------------------------------------


def test_colorbar_is_appended_to_the_right_of_an_upscaled_small_map():
    out = apply_display_style(RAMP, {"colormap": "viridis", "colorbar": True})
    upscale = colorbar_upscale(32)
    assert upscale * 32 >= COLORBAR_MIN_HEIGHT
    assert out.shape[0] == 32 * upscale
    assert out.shape[1] > 32 * upscale  # the strip is on the right
    data_area = out[:, : 32 * upscale]
    reference = apply_display_style(RAMP, {"colormap": "viridis"})
    np.testing.assert_allclose(data_area[::upscale, ::upscale], reference)
    strip = out[:, 32 * upscale :]
    assert (strip.max(axis=-1) < 0.2).sum() > 100  # black text and ticks are drawn
    assert 0.0 <= out.min() and out.max() <= 1.0


def test_large_maps_are_not_upscaled():
    big = np.random.default_rng(0).random((300, 400))
    out = apply_display_style(big, {"colormap": "magma", "colorbar": True})
    assert out.shape[0] == 300
    assert heatmap_geometry(big, {"colorbar": True})[:3] == (1, 300, 400)


def test_colorbar_text_height_stays_legible():
    """Labels are drawn at least 12 display pixels tall, whatever the map size."""
    for size in (4, 32, 128):
        out = apply_display_style(np.random.default_rng(1).random((size, size)), {"colorbar": True})
        strip = out[:, out.shape[0] :]  # square map: the strip starts at width == height
        dark_rows = np.flatnonzero((strip.max(axis=-1) < 0.3).any(axis=1))
        assert out.shape[0] >= 128
        assert dark_rows.size > 0


def test_colorbar_without_colormap_uses_gray():
    out = apply_display_style(RAMP, {"colorbar": True})
    upscale = colorbar_upscale(32)
    left, right = out[0, 0], out[0, 32 * upscale - 1]
    np.testing.assert_allclose(left, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(right, [1.0, 1.0, 1.0])


RANGES = [(1.0, 4.2), (-0.39, 0.39), (0.0, 255.0), (1e-4, 3e-3), (0.0, 1e6), (-3.7, 12.3), (0.0, 1.0), (2.0, 2.0)]


def _decimals_of(text):
    return len(text.split(".")[1]) if "." in text else 0


@pytest.mark.parametrize("vmin, vmax", RANGES)
def test_colorbar_labels_share_their_decimals(vmin, vmax):
    labels, exponent = colorbar_scale(vmin, vmax)
    texts = [text for _, text, _ in labels]
    assert len({_decimals_of(text) for text in texts}) == 1, texts
    assert not any("e" in text for text in texts), texts  # large / small values: one multiplier instead
    # each end is written close to its true value (4.2, not 4)
    for value, text, is_end in labels:
        if is_end and vmax > vmin:
            assert abs(float(text) * 10.0**exponent - value) <= 0.005 * (vmax - vmin)


def test_colorbar_labels_examples():
    def texts(vmin, vmax):
        labels, exponent = colorbar_scale(vmin, vmax)
        return [text for _, text, _ in labels], exponent

    assert texts(1.0, 4.2) == (["1.0", "4.2", "1.0", "2.0", "3.0", "4.0"], 0)
    assert texts(-0.39, 0.39)[0][:2] == ["-0.39", "0.39"]
    assert "0.00" in texts(-0.39, 0.39)[0]  # never "-0.00"
    assert texts(0.0, 255.0)[0][:2] == ["0", "255"]
    assert texts(1e-4, 3e-3) == (["0.1", "3.0", "1.0", "2.0", "3.0"], -3)
    assert texts(0.0, 1e6)[1] == 6
    assert texts(2.0, 2.0) == (["2"], 0)
    assert colorbar_header(-3, "m") == "\u00d710\u207b\u00b3 m"
    assert colorbar_header(0, "dB") == "dB"
    assert colorbar_header(0, None) == ""


@pytest.mark.parametrize("vmin, vmax", RANGES)
@pytest.mark.parametrize("bar_h", [40, 230, 900])
def test_colorbar_keeps_both_ends_and_drops_overlapping_ticks(vmin, vmax, bar_h):
    labels, _ = colorbar_scale(vmin, vmax)
    placed = place_colorbar_labels(labels, vmin, vmax, 10, bar_h, 15.0)
    ends = [text for _, text, is_end in labels if is_end]
    assert [text for _, text in placed[: len(ends)]] == ends
    ys = sorted(y for y, _ in placed)
    assert all(b - a >= 15.0 for a, b in zip(ys, ys[1:])) or len(ends) == 2 and len(placed) == 2


def _strip_text_columns(strip):
    """Columns holding dark (text) pixels right of the bar."""
    dark = (strip.mean(axis=-1) < 0.5).any(axis=0)
    return np.flatnonzero(dark)


def test_unit_is_written_once_not_on_every_tick():
    with_unit = colorbar_strip(matplotlib.colormaps["viridis"], 1.0, 4.2, 256, unit="log10 |F|")
    without = colorbar_strip(matplotlib.colormaps["viridis"], 1.0, 4.2, 256)
    # the tick labels keep their width: the unit sits above the bar
    assert with_unit.shape[1] <= max(without.shape[1], 100)
    # and the header row has text where the plain strip has none
    top = slice(0, 6)  # above the top end label
    assert (with_unit[top].mean(axis=-1) < 0.5).any() and not (without[top].mean(axis=-1) < 0.5).any()


def test_colorbar_text_becomes_a_vertical_label():
    plain = apply_display_style(RAMP, {"colormap": "viridis", "colorbar": True})
    labelled = apply_display_style(RAMP, {"colormap": "viridis", "colorbar": "error (px)"})
    assert labelled.shape[0] == plain.shape[0] and labelled.shape[1] > plain.shape[1]
    np.testing.assert_array_equal(labelled[:, : plain.shape[1] - 10], plain[:, : plain.shape[1] - 10])


@pytest.mark.parametrize("size", [16, 64, 300, 1200])
@pytest.mark.parametrize("vmin, vmax", [(1.0, 4.2), (2.0, 2.0), (1e-4, 3e-3)])
def test_colorbar_on_tiny_and_large_maps(size, vmin, vmax):
    data = np.linspace(vmin, vmax, size * size).reshape(size, size)
    out = apply_display_style(data, {"colormap": "viridis", "colorbar": True, "unit": "dB"})
    upscale = colorbar_upscale(size, size)
    assert out.shape[0] == size * upscale
    assert out.shape[1] > size * upscale


def test_constant_map_with_colorbar_does_not_fail():
    out = apply_display_style(np.full((8, 8), 2.0), {"colormap": "viridis", "colorbar": True})
    assert out.ndim == 3 and out.shape[-1] == 3


# ---------------------------------------------------------------------------
# center
# ---------------------------------------------------------------------------


def test_center_makes_the_range_symmetric():
    data = np.array([[-1.0, 0.0, 3.0]])
    out = apply_display_style(data, {"colormap": "RdBu", "center": 0})
    cmap = matplotlib.colormaps["RdBu"]
    # range [-3, 3]: 0 is the middle of the colormap, -1 is at 1/3
    np.testing.assert_allclose(out[0, 1], cmap(0.5)[:3])
    np.testing.assert_allclose(out[0, 0], cmap(1.0 / 3.0)[:3])
    np.testing.assert_allclose(out[0, 2], cmap(1.0)[:3])


def test_center_widens_explicit_bounds():
    data = np.array([[0.0, 1.0]])
    out = apply_display_style(data, {"colormap": "RdBu", "vmin": -1, "vmax": 4, "center": 1})
    cmap = matplotlib.colormaps["RdBu"]
    # |4 - 1| > |-1 - 1|: range [-2, 4], 1 is the middle
    np.testing.assert_allclose(out[0, 1], cmap(0.5)[:3])


# ---------------------------------------------------------------------------
# NaN / masked / inf
# ---------------------------------------------------------------------------


def test_nan_is_magenta_and_ignored_by_the_auto_range():
    data = np.array([[0.0, np.nan, 2.0]])
    out = apply_display_style(data, {"colormap": "viridis"})
    np.testing.assert_allclose(out[0, 1], BAD_COLOR)
    np.testing.assert_allclose(out[0, 2], matplotlib.colormaps["viridis"](1.0)[:3])


def test_masked_values_are_magenta():
    data = np.ma.masked_array([[0.0, 100.0, 2.0]], mask=[[False, True, False]])
    out = apply_display_style(data, {"colormap": "viridis"})
    np.testing.assert_allclose(out[0, 1], BAD_COLOR)
    # the masked 100 does not stretch the range
    np.testing.assert_allclose(out[0, 2], matplotlib.colormaps["viridis"](1.0)[:3])


def test_inf_goes_to_the_ends_of_the_scale():
    data = np.array([[0.0, np.inf, -np.inf, 2.0]])
    out = apply_display_style(data, {"colormap": "viridis"})
    cmap = matplotlib.colormaps["viridis"]
    np.testing.assert_allclose(out[0, 1], cmap(1.0)[:3])
    np.testing.assert_allclose(out[0, 2], cmap(0.0)[:3])


def test_nan_without_colormap_promotes_to_rgb():
    out = apply_display_style(np.array([[0.0, np.nan, 1.0]]), {"vmin": 0, "vmax": 1})
    assert out.shape == (1, 3, 3)
    np.testing.assert_allclose(out[0, 1], BAD_COLOR)
    np.testing.assert_allclose(out[0, 2], [1.0, 1.0, 1.0])
    # no NaN: still a 2D windowed array, as before
    assert apply_display_style(np.array([[0.0, 1.0]]), {"vmin": 0, "vmax": 1}).shape == (1, 2)


def test_colormap_object_bad_color_is_honoured():
    cmap = matplotlib.colormaps["viridis"].with_extremes(bad="black")
    out = apply_display_style(np.array([[0.0, np.nan]]), {"colormap": cmap})
    np.testing.assert_allclose(out[0, 1], [0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Through layout.style and a pipeline
# ---------------------------------------------------------------------------


@interactive()
def diverging(img):
    layout.style("div", colormap="RdBu", center=0, colorbar=True, unit="dB")
    return img[..., 0] * 20.0 - 5.0


def diverging_pipeline(img):
    div = diverging(img)
    return div


@interactive()
def bad_center(img):
    layout.style("out", center="zero")
    return img


def bad_center_pipeline(img):
    out = bad_center(img)
    return out


def test_snapshot_shows_the_colorbar():
    pipe = HeadlessPipeline.from_function(diverging_pipeline)
    img = np.random.default_rng(2).random((32, 32, 3))
    rendered = pipe.snapshot(None, img)
    assert rendered.shape[1] > rendered.shape[0] * 1.1  # wider than the square map: the bar is there


def test_non_numeric_center_raises():
    pipe = HeadlessPipeline.from_function(bad_center_pipeline)
    with pytest.raises(FilterError) as exc_info:
        pipe(np.zeros((4, 4)))
    assert isinstance(exc_info.value.original_error, TypeError)
    assert "center" in str(exc_info.value.original_error)


def test_qt_readout_reports_the_scalar_in_data_pixels():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(diverging_pipeline)
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="readout")
    img = np.random.default_rng(3).random((16, 16, 3))
    gui.pipeline.inputs = [img]
    gui.window.refresh()
    view = gui.window.image_canvas[0][0]["image"]
    upscale = colorbar_upscale(16)
    assert view.readout[:3] == (upscale, 16, 16)
    x0, y0, _, _ = view.image_rect()
    scale = view.scale()

    def at(display_x, display_y):
        return view.pixel_at(x0 + (display_x + 0.5) * scale, y0 + (display_y + 0.5) * scale)

    x, y, value = at(5 * upscale + 1, 9 * upscale + 2)
    assert (x, y) == (5, 9)
    assert value == pytest.approx(img[9, 5, 0] * 20.0 - 5.0)
    # in the colorbar: no value
    assert at(16 * upscale + 4, 3)[2] is None
    gui.close()


# ---------------------------------------------------------------------------
# Review fixes
# ---------------------------------------------------------------------------


def test_zero_valued_options_alone_make_a_heatmap():
    """vmin=0 / center=0 are values, not "unset" (0 == False)."""
    np.testing.assert_allclose(apply_display_style(np.array([[1.0, 2.0]]), {"center": 0}), [[0.75, 1.0]])
    out = apply_display_style(np.array([[np.nan, 1.0]]), {"vmin": 0})
    np.testing.assert_allclose(out[0, 0], BAD_COLOR)


def test_custom_colormap_object_with_colorbar():
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap

    for cmap in (ListedColormap(["red", "blue"]), LinearSegmentedColormap.from_list("mine", ["k", "y"])):
        out = apply_display_style(RAMP, {"colormap": cmap, "colorbar": True})
        assert out.shape[0] == 32 * colorbar_upscale(32)


def test_registered_colormap_strips_are_cached():
    from interactive_pipe.graphical.display import _cached_colorbar_strip

    _cached_colorbar_strip.cache_clear()
    apply_display_style(RAMP, {"colormap": "viridis", "colorbar": True})
    apply_display_style(RAMP, {"colormap": "viridis", "colorbar": True})
    assert _cached_colorbar_strip.cache_info().hits == 1


def test_wide_flat_maps_are_not_blown_up():
    out = apply_display_style(np.zeros((8, 2000)), {"colorbar": True})
    assert out.shape[1] < 2100
    assert heatmap_geometry(np.zeros((8, 2000)), {"colorbar": True})[:3] == (1, 8, 2000)


def test_numpy_integer_style_values_do_not_wrap():
    from interactive_pipe.graphical.display import heatmap_range

    data = np.zeros((2, 2))
    style = {"vmin": np.uint8(10), "vmax": np.uint8(200), "center": 128}
    assert heatmap_range(data, np.ones((2, 2), bool), style) == (10.0, 246.0)


def test_constant_map_takes_the_middle_colour_of_the_scale():
    """A zero error map with center=0 is the colour of zero (white for RdBu), not the low end."""
    from matplotlib import colormaps

    from interactive_pipe.graphical.display import apply_display_style

    shown = apply_display_style(np.zeros((8, 8)), {"colormap": "RdBu_r", "center": 0})
    np.testing.assert_allclose(shown[4, 4, :3], colormaps["RdBu_r"](0.5)[:3], atol=1 / 255)


def test_label_key_is_supported_and_equals_a_colorbar_string(caplog):
    from interactive_pipe.core.context import SUPPORTED_STYLE_KEYS

    assert "label" in SUPPORTED_STYLE_KEYS  # layout.style(..., label=...) does not warn
    by_label = apply_display_style(RAMP, {"colormap": "viridis", "colorbar": True, "label": "error (px)"})
    by_string = apply_display_style(RAMP, {"colormap": "viridis", "colorbar": "error (px)"})
    np.testing.assert_array_equal(by_label, by_string)
