"""Mouse input on the Dear PyGui backend (no viewport: the mouse is monkeypatched)."""

import numpy as np
import pytest

dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")

from interactive_pipe import PointControl, RegionControl, interactive, layout, to_pixels  # noqa: E402
from interactive_pipe.graphical import dpg_backend, dpg_image  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402

dpg = dpg_backend.dpg
IMAGE = np.random.default_rng(2).random((100, 200, 3)) * 0.5
HEATMAP = np.linspace(0.0, 1.0, 20 * 30).reshape(20, 30)


@pytest.fixture(autouse=True)
def _fresh_dpg_context():
    yield
    dpg_backend.destroy_context()


@interactive(
    dp_seed=PointControl((0.5, 0.5), name="dp_seed"),
    dp_roi=RegionControl((0.25, 0.25, 0.75, 0.75), name="dp_roi"),
)
def dp_probe(img, dp_seed=(0.5, 0.5), dp_roi=(0.25, 0.25, 0.75, 0.75)):
    col, row = to_pixels(dp_seed, img)
    x0, y0, x1, y1 = to_pixels(dp_roi, img)
    return img[y0:y1, x0:x1], img[row, :, 0]


def dp_pipeline(img):
    crop, profile = dp_probe(img)
    return [img, crop, profile]


@interactive(dh_seed=PointControl((0.5, 0.5), on="heat", name="dh_seed"))
def dh_probe(heat, dh_seed=(0.5, 0.5)):
    layout.style("heat", colorbar=True)
    col, row = to_pixels(dh_seed, heat)
    return f"{heat[row, col]:.4f}"


def dh_pipeline(heat):
    value = dh_probe(heat)
    return [heat, value]


class FakeMouse:
    """Mouse position (viewport coordinates) and buttons / keys as dpg would report them."""

    def __init__(self, monkeypatch, window):
        self.window = window
        self.pos = (0.0, 0.0)
        self.shift = False
        self.origin = {}
        monkeypatch.setattr(dpg, "get_mouse_pos", lambda local=False: list(self.pos))
        monkeypatch.setattr(dpg, "is_mouse_button_down", lambda button: True)
        monkeypatch.setattr(dpg_gui, "_shift_down", lambda: self.shift)
        monkeypatch.setattr(dpg, "get_item_rect_min", lambda item: self.origin.get(item, (0.0, 0.0)))
        monkeypatch.setattr(window, "image_cell_at", self._cell_at)

    def _cell_at(self, pos):
        for cell in self.window.image_cells():
            x0, y0 = self.origin.get(cell["content"], (0.0, 0.0))
            width, height = dpg_image.image_box(cell)
            local = (pos[0] - x0, pos[1] - y0)
            if 0 <= local[0] < width and 0 <= local[1] < height:
                return cell, local
        return None

    def at(self, cell, u, v):
        """Viewport position over image pixel coordinates (u, v) of `cell`."""
        x, y, width, _ = self.window.view.image_rect(dpg_image.image_box(cell), cell["natural_size"])
        scale = width / cell["natural_size"][0]
        x0, y0 = self.origin.get(cell["content"], (0.0, 0.0))
        return (x0 + round(x) + u * scale, y0 + round(y) + v * scale)

    def press(self, pos, shift=False):
        self.pos, self.shift = pos, shift
        self.window.on_mouse_click()

    def move(self, pos):
        self.pos = pos
        self.window.on_mouse_move(None, list(pos))

    def release(self, pos):
        self.pos = pos
        self.window.on_mouse_release()

    def click(self, pos, shift=False):
        self.press(pos, shift)
        self.release(pos)


def _gui(monkeypatch, pipe_func, inputs):
    pipeline = HeadlessPipeline.from_function(pipe_func, inputs=["img" if pipe_func is dp_pipeline else "heat"])
    for ctrl in pipeline.controls:
        ctrl.update(ctrl.value_default)
    gui = dpg_gui.InteractivePipeDPG(pipeline=pipeline, name="pointer dpg")
    gui.pipeline.inputs = inputs
    window = gui.window
    window.refresh()
    mouse = FakeMouse(monkeypatch, window)
    cells = window.image_canvas[0]
    mouse.origin = {cells[0]["content"]: (10.0, 30.0)}
    if cells[1] is not None and cells[1].get("content") is not None:
        mouse.origin[cells[1]["content"]] = (10.0 + dpg_image.image_box(cells[0])[0] + 10, 30.0)
    return gui, window, mouse


def _run_pending(window):
    if window._refresh_pending:
        window.refresh()


def test_no_widget_for_pointer_controls(monkeypatch):
    _, window, _ = _gui(monkeypatch, dp_pipeline, [IMAGE])
    assert "dp_seed" not in window.widget_list and "dp_roi" not in window.widget_list
    assert set(window.ctrl) >= {"dp_seed", "dp_roi"}


def test_click_sets_point_and_reruns(monkeypatch):
    gui, window, mouse = _gui(monkeypatch, dp_pipeline, [IMAGE])
    cell = window.image_canvas[0][0]
    mouse.click(mouse.at(cell, 40.5, 30.5))
    seed = window.ctrl["dp_seed"].value
    assert to_pixels(seed, IMAGE) == (40, 30)
    assert window._refresh_pending
    _run_pending(window)
    np.testing.assert_array_equal(gui.pipeline.results[0][2], IMAGE[30, :, 0])


def test_shift_drag_draws_region_without_panning(monkeypatch):
    gui, window, mouse = _gui(monkeypatch, dp_pipeline, [IMAGE])
    cell = window.image_canvas[0][0]
    window.view.zoom_by(2.0, dpg_image.image_box(cell), cell["natural_size"])
    view_before = (window.view.zoom, window.view.center)
    # zoomed 2x on the centre: image pixels [50, 150] x [25, 75] are visible
    mouse.press(mouse.at(cell, 60, 30), shift=True)
    assert window._drag is None
    mouse.move(mouse.at(cell, 90, 50))
    assert window.ctrl["dp_roi"].value == pytest.approx((0.3, 0.3, 0.45, 0.5))
    mouse.release(mouse.at(cell, 140, 70))
    assert window.ctrl["dp_roi"].value == pytest.approx((0.3, 0.3, 0.7, 0.7))
    assert (window.view.zoom, window.view.center) == view_before
    assert window.ctrl["dp_seed"].value == (0.5, 0.5)
    _run_pending(window)
    assert gui.pipeline.results[0][1].shape == (40, 80, 3)


def test_plain_drag_pans_and_leaves_the_point(monkeypatch):
    _, window, mouse = _gui(monkeypatch, dp_pipeline, [IMAGE])
    cell = window.image_canvas[0][0]
    window.view.zoom_by(4.0, dpg_image.image_box(cell), cell["natural_size"])
    center_before = window.view.center
    start = mouse.at(cell, 100, 50)
    mouse.press(start)
    mouse.move((start[0] + 40, start[1] + 20))
    mouse.release((start[0] + 40, start[1] + 20))
    assert window.view.center != center_before
    assert window.ctrl["dp_seed"].value == (0.5, 0.5)


def test_click_on_a_zoomed_view_maps_to_the_image(monkeypatch):
    _, window, mouse = _gui(monkeypatch, dp_pipeline, [IMAGE])
    cell = window.image_canvas[0][0]
    window.view.zoom_by(3.0, dpg_image.image_box(cell), cell["natural_size"], anchor=(20.0, 20.0))
    mouse.click(mouse.at(cell, 70.5, 20.5))
    assert to_pixels(window.ctrl["dp_seed"].value, IMAGE) == (70, 20)


def test_other_cells_are_ignored(monkeypatch):
    _, window, mouse = _gui(monkeypatch, dp_pipeline, [IMAGE])
    crop_cell = window.image_canvas[0][1]
    mouse.click(mouse.at(crop_cell, 5, 5))
    assert window.ctrl["dp_seed"].value == (0.5, 0.5)


def test_overlay_is_drawn_and_follows_zoom(monkeypatch):
    _, window, mouse = _gui(monkeypatch, dp_pipeline, [IMAGE])
    cell = window.image_canvas[0][0]
    assert cell["overlay"] == [
        ("region", pytest.approx((50.0, 25.0, 150.0, 75.0)), "dp_roi"),
        ("point", pytest.approx((100.0, 50.0)), "dp_seed"),
    ]
    assert len(cell["overlay_drawn"]) > 0
    assert all(dpg.does_item_exist(item) for item in cell["overlay_drawn"])
    assert not window.image_canvas[0][1].get("overlay")

    def rectangle_min():
        rect = next(item for item in cell["overlay_drawn"] if dpg.get_item_type(item).endswith("mvDrawRect"))
        return tuple(dpg.get_item_configuration(rect)["pmin"][:2])

    box = dpg_image.image_box(cell)
    x, y, width, _ = window.view.image_rect(box, cell["natural_size"])
    scale = width / 200
    assert rectangle_min() == pytest.approx((round(x) + 50 * scale, round(y) + 25 * scale))
    window.view.zoom_by(2.0, box, cell["natural_size"])
    window.apply_view()
    x, y, width, _ = window.view.image_rect(box, cell["natural_size"])
    scale = width / 200
    assert rectangle_min() == pytest.approx((round(x) + 50 * scale, round(y) + 25 * scale))
    # a click moves the marker at once, before the pipeline runs again
    mouse.click(mouse.at(cell, 80, 40))
    point = [item for item in cell["overlay"] if item[0] == "point"][0]
    assert point[1] == pytest.approx((80, 40))


def test_heatmap_with_colorbar_maps_to_data_pixels(monkeypatch):
    gui, window, mouse = _gui(monkeypatch, dh_pipeline, [HEATMAP])
    cell = window.image_canvas[0][0]
    natural_w, natural_h = cell["natural_size"]
    upscale = natural_h // 20
    assert upscale > 1 and natural_w > 30 * upscale
    mouse.click(mouse.at(cell, 6.5 * upscale, 4.5 * upscale))
    seed = window.ctrl["dh_seed"].value
    assert to_pixels(seed, HEATMAP) == (6, 4)
    _run_pending(window)
    assert gui.pipeline.results[0][1] == f"{HEATMAP[4, 6]:.4f}"
    mouse.click(mouse.at(cell, natural_w - 5, 10))  # on the colorbar
    assert window.ctrl["dh_seed"].value == seed
