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
    view.reset()
    view.zoom_by(2.0, BOX, SIZE)
    x, y, _, _ = view.image_rect(BOX, SIZE)
    view.pan_by(10, -5, BOX, SIZE)
    assert view.image_rect(BOX, SIZE)[:2] == pytest.approx((x + 10, y - 5))


def test_zoom_out_stops_at_fit_and_recenters():
    view = ViewState()
    view.zoom_by(4.0, BOX, SIZE, (10.0, 10.0))  # zoomed in off-center
    view.zoom_by(1e-12, BOX, SIZE, (190.0, 90.0))
    assert view.zoom == pytest.approx(1.0)
    assert view.mode == "fit"
    assert view.image_rect(BOX, SIZE) == pytest.approx((0, 0, 200, 100))
    assert MIN_ZOOM < view.min_zoom(BOX, SIZE)


def test_an_image_that_fits_stays_centered():
    view = ViewState()
    view.pan_by(50, 30, BOX, SIZE)  # fit: nothing to pan
    assert view.mode == "fit"
    # wider box: the image fits horizontally, so only the vertical pan applies
    box = (400.0, 100.0)
    view.zoom_by(2.0, box, SIZE)  # 40x20 -> fit 5 -> 10: 400x200
    view.zoom_by(0.75, box, SIZE)  # 300x150: fits horizontally only
    view.pan_by(40, 20, box, SIZE)
    x, y, w, h = view.image_rect(box, SIZE)
    assert x == pytest.approx((box[0] - w) / 2.0)
    assert y != pytest.approx((box[1] - h) / 2.0)


def test_actual_size_zoom_out_stops_at_fit_or_native_size():
    view = ViewState()
    view.set_mode("1:1")
    # a small image shown at native size does not shrink further
    view.zoom_by(0.1, BOX, SIZE)
    assert view.image_rect(BOX, SIZE) == pytest.approx((80, 40, 40, 20))
    # a large image stops at the fit size, centered
    big = (800.0, 400.0)  # fit scale 0.25
    view.zoom_by(0.01, BOX, big)
    assert view.image_rect(BOX, big) == pytest.approx((0, 0, 200, 100))


def test_zoomed_in_pan_stops_at_the_image_edges():
    view = ViewState()
    view.zoom_by(2.0, BOX, SIZE)  # 400x200 in a 200x100 box
    view.pan_by(1000, 1000, BOX, SIZE)
    assert view.image_rect(BOX, SIZE)[:2] == pytest.approx((0, 0))
    view.pan_by(-5000, -5000, BOX, SIZE)
    x, y, w, h = view.image_rect(BOX, SIZE)
    assert (x + w, y + h) == pytest.approx(BOX)
    # zooming near a corner keeps the edges out of the box too
    view.reset()
    view.zoom_by(1.25, BOX, SIZE, (0.0, 0.0))
    view.zoom_by(1.0 / 1.1, BOX, SIZE, (199.0, 99.0))
    x, y, w, h = view.image_rect(BOX, SIZE)
    assert x <= 1e-9 and y <= 1e-9 and x + w >= BOX[0] - 1e-9 and y + h >= BOX[1] - 1e-9
