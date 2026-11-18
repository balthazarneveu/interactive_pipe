"""Mouse input on the Qt backend (offscreen): QTest clicks and shift-drags on the image views."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")

from interactive_pipe import PointControl, RegionControl, interactive, layout, to_pixels  # noqa: E402
from interactive_pipe.graphical.qt_backend import PYQTVERSION  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

if PYQTVERSION == 6:
    QtTest = pytest.importorskip("PyQt6.QtTest")
    from PyQt6.QtCore import QPoint, Qt
else:  # pragma: no cover - other bindings
    pytest.skip("pointer Qt tests written for PyQt6", allow_module_level=True)

QTest = QtTest.QTest
IMAGE = np.random.default_rng(1).random((100, 200, 3)) * 0.5
HEATMAP = np.linspace(0.0, 1.0, 20 * 30).reshape(20, 30)
LEFT = Qt.MouseButton.LeftButton
SHIFT = Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


@interactive(
    qp_seed=PointControl((0.5, 0.5), name="qp_seed"),
    qp_roi=RegionControl((0.25, 0.25, 0.75, 0.75), name="qp_roi"),
)
def qp_probe(img, qp_seed=(0.5, 0.5), qp_roi=(0.25, 0.25, 0.75, 0.75)):
    col, row = to_pixels(qp_seed, img)
    x0, y0, x1, y1 = to_pixels(qp_roi, img)
    return img[y0:y1, x0:x1], img[row, :, 0]


def qp_pipeline(img):
    crop, profile = qp_probe(img)
    return [img, crop, profile]


@interactive(qh_seed=PointControl((0.5, 0.5), on="heat", name="qh_seed"))
def qh_probe(heat, qh_seed=(0.5, 0.5)):
    layout.style("heat", colorbar=True)
    col, row = to_pixels(qh_seed, heat)
    return f"{heat[row, col]:.4f}"


def qh_pipeline(heat):
    value = qh_probe(heat)
    return [heat, value]


def _gui(pipe_func, inputs, **kwargs):
    pipeline = HeadlessPipeline.from_function(pipe_func, inputs=["img" if pipe_func is qp_pipeline else "heat"])
    for ctrl in pipeline.controls:
        ctrl.update(ctrl.value_default)
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="pointer qt", **kwargs)
    gui.pipeline.inputs = inputs
    window = gui.window
    window.refresh()
    window.resize(800, 500)
    window.show()
    _settle()
    return gui


def _settle():
    for _ in range(5):
        qt_gui.QApplication.processEvents()


def _view(gui, row=0, col=0):
    return gui.window.image_canvas[row][col]["image"]


def _at(view, u, v):
    """Widget point over image pixel coordinates (u, v) of the view's pixmap."""
    x0, y0, _, _ = view.image_rect()
    s = view.scale()
    return QPoint(int(round(x0 + u * s)), int(round(y0 + v * s)))


def _close(gui):
    gui.window.close()
    _settle()


def test_no_widget_for_pointer_controls():
    gui = _gui(qp_pipeline, [IMAGE])
    assert "qp_seed" not in gui.window.widget_list
    assert "qp_roi" not in gui.window.widget_list
    assert gui.window.ctrl["qp_seed"].value == (0.5, 0.5)
    _close(gui)


def test_click_sets_point_and_reruns():
    gui = _gui(qp_pipeline, [IMAGE])
    view = _view(gui)
    QTest.mouseClick(view, LEFT, NONE, _at(view, 40.5, 30.5))
    _settle()
    seed = gui.window.ctrl["qp_seed"].value
    assert to_pixels(seed, IMAGE) == (40, 30)
    assert gui.pipeline.parameters["qp_probe"]["qp_seed"] == seed
    np.testing.assert_array_equal(gui.window._raw_outputs[0][2], IMAGE[30, :, 0])
    _close(gui)


def test_shift_drag_draws_region_without_panning():
    gui = _gui(qp_pipeline, [IMAGE])
    view = _view(gui)
    rect_before = view.image_rect()
    QTest.mousePress(view, LEFT, SHIFT, _at(view, 20, 10))
    QTest.mouseMove(view, _at(view, 60, 50))
    _settle()
    assert gui.window.ctrl["qp_roi"].value == pytest.approx((0.1, 0.1, 0.3, 0.5), abs=0.01)
    QTest.mouseRelease(view, LEFT, SHIFT, _at(view, 120, 90))
    _settle()
    roi = gui.window.ctrl["qp_roi"].value
    assert roi == pytest.approx((0.1, 0.1, 0.6, 0.9), abs=0.01)
    x0, y0, x1, y1 = to_pixels(roi, IMAGE)
    assert gui.window._raw_outputs[0][1].shape == (y1 - y0, x1 - x0, 3)
    assert view.image_rect() == pytest.approx(rect_before)
    assert gui.window.ctrl["qp_seed"].value == (0.5, 0.5)
    _close(gui)


def test_plain_drag_pans_and_leaves_the_point():
    gui = _gui(qp_pipeline, [IMAGE])
    view = _view(gui)
    view.zoom_by(4.0)  # zoomed in: there is room to pan
    rect_before = view.image_rect()
    QTest.mousePress(view, LEFT, NONE, _at(view, 100, 50))
    QTest.mouseMove(view, view.rect().center() + QPoint(40, 20))
    QTest.mouseRelease(view, LEFT, NONE, view.rect().center() + QPoint(40, 20))
    _settle()
    assert view.image_rect()[:2] != pytest.approx(rect_before[:2])
    assert gui.window.ctrl["qp_seed"].value == (0.5, 0.5)
    view.reset_view()
    _close(gui)


def test_click_on_a_zoomed_view_maps_to_the_image():
    gui = _gui(qp_pipeline, [IMAGE])
    view = _view(gui)
    view.zoom_by(3.0, anchor=(view.width() / 4.0, view.height() / 4.0))
    QTest.mouseClick(view, LEFT, NONE, _at(view, 70.5, 20.5))
    _settle()
    assert to_pixels(gui.window.ctrl["qp_seed"].value, IMAGE) == (70, 20)
    view.reset_view()
    _close(gui)


def test_clicks_elsewhere_are_ignored():
    gui = _gui(qp_pipeline, [IMAGE])
    view = _view(gui)
    QTest.mouseClick(view, LEFT, NONE, _at(view, -20, 50))  # beside the image
    QTest.mouseClick(view, Qt.MouseButton.RightButton, NONE, _at(view, 10, 10))
    crop_view = _view(gui, 0, 1)  # not the target
    QTest.mouseClick(crop_view, LEFT, NONE, _at(crop_view, 5, 5))
    _settle()
    assert gui.window.ctrl["qp_seed"].value == (0.5, 0.5)
    _close(gui)


def test_overlay_items_follow_the_values():
    gui = _gui(qp_pipeline, [IMAGE])
    view = _view(gui)
    assert view.overlay == [
        ("region", pytest.approx((50.0, 25.0, 150.0, 75.0)), "qp_roi"),
        ("point", pytest.approx((100.0, 50.0)), "qp_seed"),
    ]
    assert _view(gui, 0, 1).overlay == []
    QTest.mouseClick(view, LEFT, NONE, _at(view, 10, 20))
    _settle()
    point = [item for item in view.overlay if item[0] == "point"][0]
    assert point[1] == pytest.approx((10, 20), abs=1.0)
    _close(gui)


def test_overlay_is_painted():
    gui = _gui(qp_pipeline, [IMAGE * 0.0])  # black image: any colour comes from the overlay
    view = _view(gui)
    grab = view.grab().toImage()
    x0, y0, _, _ = view.image_rect()
    s = view.scale()
    color = grab.pixelColor(int(x0 + 100 * s), int(y0 + 50 * s))  # point centre
    assert (color.red(), color.green(), color.blue()) != (0, 0, 0)
    edge = grab.pixelColor(int(x0 + 100 * s), int(round(y0 + 25 * s)))  # top edge of the region
    assert edge.blue() > 100
    _close(gui)


def test_heatmap_with_colorbar_maps_to_data_pixels():
    gui = _gui(qh_pipeline, [HEATMAP])
    view = _view(gui)
    upscale = view.readout[0]
    assert upscale > 1
    QTest.mouseClick(view, LEFT, NONE, _at(view, 6.5 * upscale, 4.5 * upscale))
    _settle()
    seed = gui.window.ctrl["qh_seed"].value
    assert to_pixels(seed, HEATMAP) == (6, 4)
    assert gui.window._raw_outputs[0][1] == f"{HEATMAP[4, 6]:.4f}"
    width = view.image_size()[0]
    QTest.mouseClick(view, LEFT, NONE, _at(view, width - 5, 10))  # on the colorbar
    _settle()
    assert gui.window.ctrl["qh_seed"].value == seed
    _close(gui)


def test_threaded_mode():
    gui = _gui(qp_pipeline, [IMAGE], threaded=True)
    view = _view(gui)
    QTest.mouseClick(view, LEFT, NONE, _at(view, 40.5, 30.5))
    deadline = time.monotonic() + 5.0  # the run happens in the worker thread
    while time.monotonic() < deadline:
        _settle()
        outputs = getattr(gui.window, "_raw_outputs", None)
        if outputs is not None and np.array_equal(outputs[0][2], IMAGE[30, :, 0]):
            break
        time.sleep(0.005)
    np.testing.assert_array_equal(gui.window._raw_outputs[0][2], IMAGE[30, :, 0])
    gui.window.stop_threaded_runs()
    _close(gui)


def test_help_lists_the_gestures(capsys):
    gui = _gui(qp_pipeline, [IMAGE])
    gui.print_message = lambda lines: None
    lines = gui.show_help()
    assert "[click] on the first image : set qp_seed" in lines
    assert "[shift+drag] on the first image : draw qp_roi" in lines
    _close(gui)


@interactive(qz_roi=RegionControl((0.1, 0.1, 0.3, 0.3), name="qz_roi"))
def qz_zoom(img, qz_roi=(0.1, 0.1, 0.3, 0.3)):
    x0, y0, x1, y1 = to_pixels(qz_roi, img)
    return np.repeat(np.repeat(img[y0:y1, x0:x1], 4, axis=0), 4, axis=1)


def qz_pipeline(img):
    crop = qz_zoom(img)
    return [img, crop]


def test_region_drag_at_1_1_keeps_the_grid_still():
    """Issue 79: at 1:1 the enlarged crop changes size while the region is
    dragged; the grid must not relayout under the mouse (the image would move,
    changing the region again, and everything flickers)."""
    pipeline = HeadlessPipeline.from_function(qz_pipeline, inputs=["img"])
    gui = qt_gui.InteractivePipeQT(pipeline=pipeline, name="pointer qt")
    gui.pipeline.inputs = [np.random.default_rng(4).random((256, 256, 3))]
    window = gui.window
    window.refresh()
    window.show()
    _settle()
    view = _view(gui)
    view.set_mode("1:1")
    _settle()
    geometry, rect, size = view.geometry().getRect(), view.image_rect(), window.size()
    QTest.mousePress(view, LEFT, SHIFT, _at(view, 20, 20))
    for k in range(1, 8):
        QTest.mouseMove(view, _at(view, 20 + 25 * k, 20 + 20 * k))
        _settle()
        assert view.geometry().getRect() == geometry
        assert view.image_rect() == pytest.approx(rect)
        assert window.size() == size
    crop = _view(gui, 0, 1)
    assert crop.image_size()[0] > crop.width()  # outgrew its cell meanwhile
    QTest.mouseRelease(view, LEFT, SHIFT, _at(view, 200, 160))
    _settle()
    assert not view.sync.gesture_active
    assert crop.minimumSizeHint().width() == crop.image_size()[0]  # the layout takes the new size
    _close(gui)
