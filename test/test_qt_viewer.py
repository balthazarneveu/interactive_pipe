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


@interactive(as_curve=(False,))
def image_or_curve(img, as_curve=False):
    if as_curve:
        return Curve([SingleCurve(y=img.mean(axis=0))], ylabel="mean")
    return img


def switching_pipeline(img):
    out = image_or_curve(img)
    return [out]


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
        window._resize_request = None  # a user resize, not the window manager answering a request
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


def test_zoom_out_stops_at_fit_and_recenters():
    window = build_window(pair_pipeline)
    settle(window, (800, 400))
    view = views(window)[0]
    view.zoom_by(4.0, (5.0, 5.0))  # zoomed in off-center
    view.pan_by(40, 25)
    view.zoom_by(1e-9, (view.width() - 5.0, view.height() - 5.0))
    assert view.sync.mode == "fit"
    assert view.scale() == pytest.approx(view.fit_scale())
    x, y, w, h = view.image_rect()
    assert x == pytest.approx((view.width() - w) / 2.0)
    assert y == pytest.approx((view.height() - h) / 2.0)
    view.pan_by(30, 30)  # nothing to pan when the image fits
    assert view.sync.mode == "fit"


def test_actual_size_zoom_out_stops_at_the_fit_size():
    window = build_window(pair_pipeline)
    settle(window, (800, 400))
    window.set_view_mode("fit")
    settle(window, (800, 400))
    view = views(window)[0]
    view.sync.absolute = True  # 1:1 scale without the window growing to the native size
    view.sync.set_state(1.0, (0.2, 0.8))
    assert view.fit_scale() < 1.0  # two 600x400 images side by side in 800 px
    view.zoom_by(1e-9)
    assert view.scale() == pytest.approx(view.fit_scale())
    x, y, w, h = view.image_rect()
    assert (x, y) == pytest.approx(((view.width() - w) / 2.0, (view.height() - h) / 2.0))


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


def test_image_curve_switches_do_not_leak_synced_views():
    window = build_window(switching_pipeline, image=RAMP[:8, :8])
    sync = window._view_sync()
    for _cycle in range(3):
        window.ctrl["as_curve"].update(True)
        window.refresh()
        assert sync.views == []  # the replaced ImageView left the sync
        window.ctrl["as_curve"].update(False)
        window.refresh()
    live_view = window.image_canvas[0][0]["image"]
    assert isinstance(live_view, ImageView) and live_view.has_image()
    assert sync.views == [live_view]
    calls = []
    live_view.zoom_in = lambda: calls.append("in")
    window.zoom_in()  # zooms through the live view
    assert calls == ["in"]


def test_zoom_uses_a_view_showing_an_image():
    window = build_window(mixed_pipeline, image=RAMP[:8, :8])
    image_view = window.image_canvas[0][0]["image"]
    sync = window._view_sync()
    sync.views.remove(image_view)
    sync.views.append(image_view)
    assert not sync.views[0].has_image()  # the text cell view comes first
    calls = []
    image_view.zoom_out = lambda: calls.append("out")
    window.zoom_out()
    assert calls == ["out"]


def test_actual_size_grows_the_window_and_fit_restores_it():
    window = build_window(pair_pipeline)
    settle(window, (400, 300))
    before = (window.width(), window.height())
    window.set_view_mode("1:1")
    settle(window)
    for view in views(window):
        assert (view.sizeHint().width(), view.sizeHint().height()) == (W, H)  # native, not the capped hint
    assert window.width() > before[0] and window.height() > before[1]
    window.set_view_mode("fit")
    settle(window)
    assert (window.width(), window.height()) == before


@interactive()
def many_sliders(
    img,
    p0=(0.5, [0.0, 1.0]),
    p1=(0.5, [0.0, 1.0]),
    p2=(0.5, [0.0, 1.0]),
    p3=(0.5, [0.0, 1.0]),
    p4=(0.5, [0.0, 1.0]),
    p5=(0.5, [0.0, 1.0]),
    p6=(0.5, [0.0, 1.0]),
    p7=(0.5, [0.0, 1.0]),
    p8=(0.5, [0.0, 1.0]),
    p9=(0.5, [0.0, 1.0]),
    p10=(0.5, [0.0, 1.0]),
    p11=(0.5, [0.0, 1.0]),
    p12=(0.5, [0.0, 1.0]),
    p13=(0.5, [0.0, 1.0]),
    p14=(0.5, [0.0, 1.0]),
    p15=(0.5, [0.0, 1.0]),
    p16=(0.5, [0.0, 1.0]),
    p17=(0.5, [0.0, 1.0]),
    p18=(0.5, [0.0, 1.0]),
    p19=(0.5, [0.0, 1.0]),
    p20=(0.5, [0.0, 1.0]),
    p21=(0.5, [0.0, 1.0]),
    p22=(0.5, [0.0, 1.0]),
    p23=(0.5, [0.0, 1.0]),
    p24=(0.5, [0.0, 1.0]),
    p25=(0.5, [0.0, 1.0]),
    p26=(0.5, [0.0, 1.0]),
    p27=(0.5, [0.0, 1.0]),
    p28=(0.5, [0.0, 1.0]),
    p29=(0.5, [0.0, 1.0]),
):
    return img * p0


def sliders_pipeline(img):
    out = many_sliders(img)
    return [out]


def test_actual_size_keeps_the_window_on_screen_and_scrolls_the_controls():
    """1:1 with more controls than the screen holds: the image shows whole at
    its native size, the window fits the screen and the controls scroll."""
    image = RAMP[:200, :300].copy()
    window = build_window(sliders_pipeline, image=image)
    controls = window.bottom_scroll
    screen = window.screen().availableGeometry()
    assert controls.widget().sizeHint().height() + 200 > screen.height()  # the test needs it
    window.set_view_mode("1:1")
    settle(window)
    (view,) = views(window)
    assert view.width() >= 300 and view.height() >= 200  # whole image (centered when wider)
    assert view.scale() == 1.0
    assert window.height() <= screen.height()
    assert controls.height() < controls.widget().sizeHint().height()
    assert controls.verticalScrollBar().maximum() > 0
    window.set_view_mode("fit")
    settle(window)
    assert window.height() <= screen.height()


def test_window_manager_shrinking_a_resize_caps_later_ones():
    """Wayland reports the panels as available screen: the size the compositor
    granted instead of a requested one becomes the limit for later fits."""
    window = build_window(pair_pipeline)
    settle(window, (600, 600))
    window._resize_request = (700, 700, qt_gui.time.monotonic(), (600, 600), False)
    window.resize(700, 700)  # Qt's echo of the request: not an answer yet
    QApplication.processEvents()
    assert window._granted_limit is None
    window.resize(700, 650)  # the compositor's answer
    QApplication.processEvents()
    assert window._granted_limit == (qt_gui.NO_LIMIT, 650)
    window._resize_request = None
    window.resize(700, 500)  # the user shrinking the window: not a limit
    QApplication.processEvents()
    assert window._granted_limit == (qt_gui.NO_LIMIT, 650)
    window.set_view_mode("1:1")
    settle(window)
    assert window.height() <= max(650, window.minimumSizeHint().height())


def rgb_pipeline(img):
    out = to_rgb(img)
    return [out]


def test_controls_area_is_hidden_without_controls():
    window = build_window(switching_pipeline)
    assert window.bottom_scroll.isVisible()
    window = build_window(rgb_pipeline)
    assert not window.bottom_scroll.isVisible()


def column_widgets(window):
    layouts = [window.bottom_panels_layout, *window._extra_columns]
    return [qt_gui.layout_widgets(layout) for layout in layouts]


def test_controls_spread_over_columns_instead_of_scrolling():
    window = build_window(sliders_pipeline, image=RAMP[:200, :300].copy())
    window.resize(1800, 700)  # wide but too short for one column of 30 sliders
    for _ in range(3):
        QApplication.processEvents()
    columns = [c for c in column_widgets(window) if c]
    assert len(columns) > 1
    assert [w for column in columns for w in column] == window._bottom_items  # order kept
    settle(window)
    assert window.bottom_scroll.verticalScrollBar().maximum() == 0  # no scroll needed
    # narrow window: back to a single column, the controls scroll
    window.resize(400, 700)
    for _ in range(3):
        QApplication.processEvents()
    settle(window)
    assert [len(c) for c in column_widgets(window) if c] == [len(window._bottom_items)]
    assert window.bottom_scroll.verticalScrollBar().maximum() > 0


def test_tall_window_keeps_a_single_column():
    window = build_window(pair_pipeline)
    assert window._update_control_columns(3000, 3000) is False
    assert not window._extra_columns


def test_stale_configure_is_not_a_limit_and_the_request_is_retried():
    """A size back below the one before the request is a stale configure: no
    limit is learned and the size is asked again (once)."""
    window = build_window(pair_pipeline)
    settle(window, (500, 400))
    window._request_resize(900, 800)
    window.resize(450, 300)  # the stale answer
    for _ in range(3):
        QApplication.processEvents()
    assert window._granted_limit is None
    assert (window.width(), window.height()) == (900, 800)
