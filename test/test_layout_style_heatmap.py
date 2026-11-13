"""layout.style heatmap options (colormap / vmin / vmax) and unknown style keys."""

import logging

import matplotlib
import numpy as np
import pytest

from interactive_pipe import FilterError, interactive, layout
from interactive_pipe.core import context as context_module
from interactive_pipe.graphical.window import InteractivePipeWindow, apply_display_style
from interactive_pipe.headless.pipeline import HeadlessPipeline

RAMP = np.linspace(0.0, 2.0, 12).reshape(3, 4)


def test_colormap_turns_a_2d_array_into_rgb():
    rgb = apply_display_style(RAMP, {"colormap": "viridis", "vmin": 0.0, "vmax": 2.0})
    assert rgb.shape == (3, 4, 3)
    viridis = matplotlib.colormaps["viridis"]
    np.testing.assert_allclose(rgb[0, 0], viridis(0.0)[:3])
    np.testing.assert_allclose(rgb[-1, -1], viridis(1.0)[:3])


def test_vmin_vmax_default_to_the_data_range():
    rgb = apply_display_style(RAMP, {"colormap": "gray"})
    np.testing.assert_allclose(rgb[0, 0], 0.0, atol=1e-6)
    np.testing.assert_allclose(rgb[-1, -1], 1.0, atol=1e-6)


def test_vmin_vmax_without_colormap_window_the_grayscale():
    gray = apply_display_style(RAMP, {"vmin": 1.0, "vmax": 2.0})
    assert gray.shape == RAMP.shape
    assert gray.min() == 0.0 and gray.max() == 1.0
    np.testing.assert_allclose(gray[0, 0], 0.0)


@pytest.mark.parametrize(
    "content, style",
    [
        (np.zeros((3, 4, 3)), {"colormap": "viridis"}),  # RGB image: untouched
        (RAMP, {"title": "only a title"}),
        (RAMP, None),
        ("text", {"colormap": "viridis"}),
    ],
)
def test_other_contents_and_styles_are_untouched(content, style):
    assert apply_display_style(content, style) is content


@interactive()
def heat(img):
    layout.style("heatmap", title="Heat", colormap="viridis", vmin=0, vmax=2)
    return img[..., 0] * 2


def heat_pipeline(img):
    heatmap = heat(img)
    return [[img, heatmap]]


class RecordingWindow(InteractivePipeWindow):
    """Backend-free window keeping what each cell would display."""

    def __init__(self, pipeline):
        super().__init__(pipeline=pipeline)
        self.cells = {}

    def add_image_placeholder(self, row, col):
        pass

    def update_image(self, content, row, col):
        self.cells[(row, col)] = content

    def convert_image(self, img):
        return img


def test_every_backend_hook_applies_the_colormap():
    pipe = HeadlessPipeline.from_function(heat_pipeline)
    img = np.full((3, 4, 3), 0.5)
    out = pipe(img)
    window = RecordingWindow(pipe)
    window.refresh_display(out)
    displayed = window.cells[(0, 1)]
    assert displayed.shape == (3, 4, 3)
    np.testing.assert_allclose(displayed[0, 0], matplotlib.colormaps["viridis"](0.5)[:3])
    assert window.cells[(0, 0)] is out[0][0]  # unstyled image untouched
    assert window.get_current_style(0, 1)["title"] == "Heat"


@interactive()
def typo_style(img):
    layout.style("out", colorbar=True, cmap="jet")
    return img


def typo_pipeline(img):
    out = typo_style(img)
    return out


def test_unknown_style_keys_warn_once_listing_the_supported_ones(caplog, monkeypatch):
    monkeypatch.setattr(context_module, "_warned_style_keys", set())
    pipe = HeadlessPipeline.from_function(typo_pipeline)
    with caplog.at_level(logging.WARNING):
        pipe(np.zeros(3))
        pipe(np.zeros(3))
    assert caplog.text.count("unknown style key 'cmap'") == 1
    assert caplog.text.count("unknown style key 'colorbar'") == 1
    assert "Supported keys: title, subtitle, colormap, vmin, vmax, xlabel, ylabel" in caplog.text


@interactive()
def bad_colormap(img):
    layout.style("out", colormap="virdis")
    return img


def bad_colormap_pipeline(img):
    out = bad_colormap(img)
    return out


def test_unknown_colormap_raises_with_suggestion():
    pipe = HeadlessPipeline.from_function(bad_colormap_pipeline)
    with pytest.raises(FilterError) as exc_info:
        pipe(np.zeros(3))
    assert "unknown colormap 'virdis'" in str(exc_info.value.original_error)
    assert "'viridis'" in str(exc_info.value.original_error)


def test_qt_backend_displays_the_heatmap_in_color():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(heat_pipeline)
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="heatmap")
    gui.pipeline.inputs = [np.full((4, 4, 3), 0.5)]
    gui.window.refresh()
    canvas = gui.window.image_canvas
    image = canvas[0][1]["image"].pixmap().toImage()
    color = image.pixelColor(0, 0)
    expected = np.round(np.array(matplotlib.colormaps["viridis"](0.5)[:3]) * 255)
    np.testing.assert_allclose([color.red(), color.green(), color.blue()], expected, atol=2)
    assert canvas[0][1]["title"].text() == "Heat"
    gui.close()


@interactive()
def subtitled(img):
    layout.style("out", title="Main", subtitle="details")
    layout.style("other", subtitle="only")
    return img


def subtitle_pipeline(img):
    out = subtitled(img)
    return out


def test_subtitle_is_appended_to_the_title():
    pipe = HeadlessPipeline.from_function(subtitle_pipeline)
    pipe(np.zeros(3))
    styles = pipe.framework_state.output_styles
    assert styles["out"]["title"] == "Main · details"
    assert styles["other"]["title"] == "other · only"
