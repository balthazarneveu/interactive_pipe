"""Zoom/pan geometry of the Dear PyGui image grid (pure Python, no dpg needed)."""

import pytest

from interactive_pipe.graphical.dpg_viewer import MAX_ZOOM, MIN_ZOOM, ZOOM_STEP, ViewState

BOX = (200.0, 100.0)
SIZE = (40.0, 20.0)  # fit scale 5


def test_fit_and_actual_size_rects():
    view = ViewState()
    assert view.mode == "fit"
    assert view.image_rect(BOX, SIZE) == pytest.approx((0, 0, 200, 100))
    view.set_mode("1:1")
    assert view.mode == "1:1"
    assert view.image_rect(BOX, SIZE) == pytest.approx((80, 40, 40, 20))


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        ViewState().set_mode("zoomed")


def test_zoom_keeps_the_anchor_point_in_place():
    view = ViewState()
    anchor = (30.0, 70.0)
    x0, y0, w0, h0 = view.image_rect(BOX, SIZE)
    before = ((anchor[0] - x0) / w0, (anchor[1] - y0) / h0)
    view.zoom_by(ZOOM_STEP, BOX, SIZE, anchor)
    x1, y1, w1, h1 = view.image_rect(BOX, SIZE)
    assert view.mode == "custom"
    assert w1 == pytest.approx(w0 * ZOOM_STEP)
    assert ((anchor[0] - x1) / w1, (anchor[1] - y1) / h1) == pytest.approx(before)


def test_zoom_is_clamped_and_pan_moves_the_image():
    view = ViewState()
    view.zoom_by(1e9, BOX, SIZE)
    assert view.zoom == MAX_ZOOM
    view.zoom_by(1e-12, BOX, SIZE)
    assert view.zoom == MIN_ZOOM
    view.reset()
    view.pan_by(10, -5, BOX, SIZE)
    assert view.image_rect(BOX, SIZE)[:2] == pytest.approx((10, -5))
