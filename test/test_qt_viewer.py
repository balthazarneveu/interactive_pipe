"""Qt image viewer tests (offscreen): fit-to-cell, resize, synced zoom/pan,
pixel readout from the raw float output, 1:1 mode and mixed layouts."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import interactive  # noqa: E402
from interactive_pipe.data_objects.curves import Curve, SingleCurve  # noqa: E402
from interactive_pipe.data_objects.table import Table  # noqa: E402
from interactive_pipe.graphical.qt_backend import QApplication  # noqa: E402
from interactive_pipe.graphical.qt_viewer import ImageView, ViewSync, pixel_value  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

H, W = 400, 600
RAMP = np.linspace(0.0, 1.0, H * W, dtype=np.float64).reshape(H, W)


@interactive()
def brighten(img, gain=(0.5, [0.0, 1.0])):
    return img * gain


@interactive()
def to_rgb(img):
    return np.stack([img, 1.0 - img, 0.25 * img], axis=-1)


def pair_pipeline(img):
    before = brighten(img)
    after = to_rgb(img)
    return before, after


@interactive()
def make_curve(img):
    return Curve([SingleCurve(y=img.mean(axis=0))], ylabel="mean")


@interactive()
def make_table(img):
    return Table(img[:2, :2], columns=["a", "b"])


@interactive()
def make_text(img):
    return f"mean={img.mean():.2f}"


def mixed_pipeline(img):
    gray = brighten(img)
    curve = make_curve(img)
    tab = make_table(img)
    txt = make_text(img)
    return [[gray, curve], [tab, txt]]


def build_window(pipeline_function, image=RAMP, size=(300, 200)):
    pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="viewer", size=size)
    gui.pipeline.inputs = [image.copy()]
    window = gui.window
    window.refresh()
    settle(window)
    return window


def settle(window, size=None):
    if size is not None:
        window.resize(*size)
    window.layout().activate()
    QApplication.processEvents()


def views(window):
    return [cell["image"] for row in window.image_canvas for cell in row if cell is not None]


def test_large_output_is_fitted_into_its_cell():
    big = np.random.default_rng(0).random((4000, 6000))
    window = build_window(pair_pipeline, image=big)
    settle(window, (500, 300))
    for view in views(window):
        assert isinstance(view, ImageView)
        assert view.pixmap().width() == 6000  # full resolution kept (save/inspect)
        x, y, w, h = view.image_rect()
        assert w <= view.width() + 1e-6 and h <= view.height() + 1e-6
        assert x >= -1e-6 and y >= -1e-6
        assert w / h == pytest.approx(6000 / 4000, rel=1e-6)
        assert max(w - view.width(), h - view.height()) == pytest.approx(0.0, abs=1e-6)
    # the window did not grow to the native image size
    assert window.width() < 6000 and window.height() < 4000


def test_window_grows_once_to_show_new_images():
    window = build_window(pair_pipeline, size=(300, 200))
    # two 600x400 images: the window grows toward their preferred size
    # (bounded by the screen), instead of staying at its minimum size
    assert window.height() > 400
    for view in views(window):
        assert view.sizeHint().width() == W and view.sizeHint().height() == H


def test_resizing_the_window_rescales_the_views():
    window = build_window(pair_pipeline)
    settle(window, (400, 250))
    view = views(window)[0]
    small = view.scale()
    settle(window, (1000, 700))
    assert view.scale() > small
    assert view.image_rect()[2] <= view.width() + 1e-6


def test_cells_share_the_space_evenly():
    window = build_window(pair_pipeline)
    settle(window, (900, 500))
    left, right = views(window)
    assert abs(left.width() - right.width()) <= 2
    assert left.height() == right.height()


def test_zoom_and_pan_are_synced_across_cells():
    window = build_window(pair_pipeline)
    settle(window, (800, 400))
    left, right = views(window)
    assert left.sync is right.sync
    assert left.image_rect() == pytest.approx(right.image_rect())
    left.zoom_in()
    assert left.sync.mode == "custom"
    assert left.scale() > left.fit_scale()
    assert right.scale() == pytest.approx(left.scale())
    assert right.image_rect() == pytest.approx(left.image_rect())
    right.pan_by(30, -10)
    assert left.image_rect() == pytest.approx(right.image_rect())
    # window-level helpers drive the shared state too
    before = left.scale()
    window.zoom_out()
    assert right.scale() == pytest.approx(before / 1.25)
    window.reset_view()
    assert left.sync.mode == "fit" and left.scale() == pytest.approx(left.fit_scale())


def test_wheel_zoom_keeps_the_point_under_the_cursor():
    window = build_window(pair_pipeline)
    settle(window, (800, 400))
    view = views(window)[0]
    anchor = (view.width() * 0.3, view.height() * 0.6)
    before = view.map_to_image(*anchor)
    view.zoom_by(2.0, anchor)
    assert view.map_to_image(*anchor) == pytest.approx(before)


def test_hover_reports_the_raw_float_value():
    window = build_window(pair_pipeline)
    settle(window, (800, 400))
    hits = []
    window.on_pixel_hover = lambda row, col, x, y, value: hits.append((row, col, x, y, value))
    gray, rgb = views(window)
    window.set_view_mode("1:1")
    x0, y0, _, _ = gray.image_rect()
    # pixel (x=10, y=20), sampled at its middle
    x, y, value = gray.pixel_at(x0 + 10.5, y0 + 20.5)
    assert (x, y) == (10, 20)
    assert isinstance(value, float)
    assert value == pytest.approx(0.5 * RAMP[20, 10])  # float, not the 8-bit display value
    _, _, rgb_value = rgb.pixel_at(x0 + 10.5, y0 + 20.5)
    assert rgb_value == pytest.approx((RAMP[20, 10], 1.0 - RAMP[20, 10], 0.25 * RAMP[20, 10]))
    assert gray.pixel_at(x0 - 5, y0 - 5)[2] is None
    gray.hover_callback(x, y, value)
    assert hits == [(0, 0, 10, 20, value)]
    # without a status callback the readout goes to the tooltip
    window.on_pixel_hover = None
    gray.hover_callback(x, y, value)
    assert gray.toolTip().startswith("(10, 20)")


def test_one_to_one_mode_shows_native_scale():
    window = build_window(pair_pipeline)
    settle(window, (300, 200))
    view = views(window)[0]
    window.set_view_mode("1:1")
    assert view.sync.mode == "1:1"
    assert view.scale() == pytest.approx(1.0)
    assert view.image_rect()[2:] == pytest.approx((W, H))
    view.zoom_in()
    assert view.scale() == pytest.approx(1.25)
    window.set_view_mode("fit")
    assert view.scale() == pytest.approx(view.fit_scale())
    with pytest.raises(ValueError):
        window.set_view_mode("zoomed")


def test_mixed_layout_text_curve_table_still_work():
    window = build_window(mixed_pipeline, image=RAMP[:8, :8])
    canvas = window.image_canvas
    assert isinstance(canvas[0][0]["image"], ImageView) and canvas[0][0]["image"].has_image()
    assert type(canvas[0][1]["image"]).__name__ != "ImageView"  # matplotlib canvas
    assert type(canvas[1][0]["image"]).__name__ != "ImageView"
    text_cell = canvas[1][1]["image"]
    assert isinstance(text_cell, ImageView) and not text_cell.has_image()
    assert text_cell.text().startswith("mean=")
    # only the image views are registered in the shared sync
    assert window._view_sync().views.count(canvas[0][0]["image"]) == 1
    window.zoom_in()  # does not crash with non-image cells around
    window.refresh()


def test_image_view_text_and_pixmap_round_trip():
    view = ImageView(sync=ViewSync())
    view.setText("hello")
    assert view.text() == "hello" and not view.has_image()
    pix = qt_gui.numpy_to_pixmap((RAMP[:4, :6] * 255).astype(np.uint8))
    view.set_image(pix, RAMP[:4, :6])
    assert view.has_image() and view.text() == ""
    assert view.minimumSizeHint().width() <= 32
    view.setText("again")
    assert not view.has_image() and view.text() == "again"


def test_pixel_value_helper():
    assert pixel_value(None, 0, 0) is None
    assert pixel_value(RAMP, -1, 0) is None
    assert pixel_value(RAMP, W, 0) is None
    assert pixel_value(RAMP, 3, 2) == pytest.approx(RAMP[2, 3])
    rgb = np.ones((2, 2, 3)) * 0.5
    assert pixel_value(rgb, 1, 1) == (0.5, 0.5, 0.5)
