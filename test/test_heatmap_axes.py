"""layout.style(extent=, xlabel=, ylabel=): axes drawn into a heatmap's image,
the same on every backend; readouts and pointer controls still map to the
right data pixel."""

import os

import numpy as np
import pytest

from interactive_pipe import FilterError, PointControl, interactive, layout
from interactive_pipe.graphical.display import apply_display_style, heatmap_geometry
from interactive_pipe.graphical.pointer_input import PointerTargets, overlay_items, to_fraction
from interactive_pipe.headless.pipeline import HeadlessPipeline

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MAP = np.arange(20 * 30, dtype=float).reshape(20, 30)
AXES = {"colormap": "viridis", "extent": (-90, 90, 0.1, 2.0), "xlabel": "angle", "ylabel": "spacing"}


def test_axes_add_margins_and_the_map_sits_at_the_geometry_offset():
    shown = apply_display_style(MAP, AXES)
    geometry = heatmap_geometry(MAP, AXES)
    assert geometry.x0 > 0 and geometry.y0 > 0
    up = geometry.upscale
    assert shown.shape[0] > 20 * up and shown.shape[1] > 30 * up
    plain = apply_display_style(MAP, {"colormap": "viridis"})
    # the data pixel (row 3, column 7), upscaled, is where the geometry says
    y, x = geometry.y0 + 3 * up + up // 2, geometry.x0 + 7 * up + up // 2
    np.testing.assert_allclose(shown[y, x], plain[3, 7], atol=1.0 / 255)
    # margins are white, with dark tick labels in them
    left_margin = shown[geometry.y0 : geometry.y0 + 20 * up, : geometry.x0 - 2]
    assert left_margin.min() < 0.3 and np.median(left_margin) > 0.99


def test_extent_coordinates_of_a_data_pixel():
    geometry = heatmap_geometry(MAP, AXES)
    x, y = geometry.data_coordinates(0, 0)  # top-left pixel centre
    assert x == pytest.approx(-90 + 3)  # 180 deg over 30 columns
    assert y == pytest.approx(2.0 - 1.9 / 40)
    x, y = geometry.data_coordinates(29, 19)
    assert x == pytest.approx(90 - 3) and y == pytest.approx(0.1 + 1.9 / 40)


def test_labels_without_extent_count_pixels_and_extent_alone_makes_a_heatmap():
    geometry = heatmap_geometry(MAP, {"colormap": "gray", "xlabel": "column"})
    assert geometry.extent is None and geometry.data_coordinates(4, 5) == (4.0, 5.0)
    gray = apply_display_style(MAP, {"extent": (0, 1, 0, 1)})
    assert gray.shape[0] > 20  # axes drawn on a gray heatmap (data range)
    # xlabel alone on a plain image is not a heatmap (matplotlib backend axes label)
    assert apply_display_style(MAP / MAP.max(), {"xlabel": "x"}) is not None
    assert heatmap_geometry(MAP, {"xlabel": "x"}) is None


def test_colorbar_runs_along_the_map_not_along_the_axes():
    style = dict(AXES, colorbar=True)
    with_bar = apply_display_style(MAP, style)
    without = apply_display_style(MAP, AXES)
    assert with_bar.shape[0] == without.shape[0]
    assert with_bar.shape[1] > without.shape[1]
    np.testing.assert_allclose(with_bar[:, : without.shape[1]], without)


def test_pointer_fraction_and_overlay_account_for_the_margins():
    point = PointControl((0.5, 0.5), name="p")
    targets = PointerTargets([point], [["heat"]], [[MAP]], {(0, 0): AXES})
    area = targets.data_size((0, 0), (999, 999))
    geometry = heatmap_geometry(MAP, AXES)
    assert tuple(area) == (30.0 * geometry.upscale, 20.0 * geometry.upscale, geometry.x0, geometry.y0)
    # the map's corners are fractions 0 and 1
    assert to_fraction(geometry.x0, geometry.y0, area) == (0.0, 0.0)
    assert to_fraction(geometry.x0 + area.width, geometry.y0 + area.height, area) == (1.0, 1.0)
    ((kind, (u, v), _),) = overlay_items(targets, (0, 0), area)
    assert (u, v) == (geometry.x0 + area.width / 2, geometry.y0 + area.height / 2)
    # plain (width, height) sizes still work
    assert to_fraction(15.0, 10.0, (30.0, 20.0)) == (0.5, 0.5)


@interactive()
def beam():
    layout.style("af", **AXES)
    return MAP.copy()


def beam_pipeline():
    af = beam()
    return af


def test_snapshot_shows_the_axes():
    rendered = HeadlessPipeline.from_function(beam_pipeline).snapshot(None)
    shown = apply_display_style(MAP, AXES)
    # the cell keeps the aspect of the map with its axes, wider than the bare map
    assert rendered.shape[1] / rendered.shape[0] > 1.0
    assert shown.shape[1] / shown.shape[0] < 30 / 20 + 0.5


def test_qt_readout_maps_through_the_margins_and_reports_extent():
    qt_gui = pytest.importorskip("interactive_pipe.graphical.qt_gui")
    pipe = HeadlessPipeline.from_function(beam_pipeline, inputs=[])
    gui = qt_gui.InteractivePipeQT(pipeline=pipe, name="axes")
    try:
        gui.pipeline.inputs = []
        gui.window.refresh()
        view = gui.window.image_canvas[0][0]["image"]
        geometry = view.readout
        assert geometry.x0 > 0 and geometry.extent == (-90, 90, 0.1, 2.0)
        x0, y0, _, _ = view.image_rect()
        scale = view.scale()
        up = geometry.upscale

        def at(display_x, display_y):
            return view.pixel_at(x0 + (display_x + 0.5) * scale, y0 + (display_y + 0.5) * scale)

        x, y, value = at(geometry.x0 + 7 * up + 1, geometry.y0 + 3 * up + 1)
        assert (x, y) == (7, 3) and value == MAP[3, 7]
        assert at(2, geometry.y0 + 5)[2] is None  # in the axes margin: no value
        gui.window._on_view_hover(view, 0, 0, 7, 3, value)
        assert "x=-45, y=1.667 (7, 3) = 97" in gui.window.status_label.text()
    finally:
        gui.close()


def test_mpl_hides_the_pixel_ticks_of_a_heatmap_with_axes():
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    pipe = HeadlessPipeline.from_function(beam_pipeline, inputs=[])
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=pipe, name="axes mpl")
    try:
        gui.pipeline.inputs = []
        gui.window.refresh()
        ax = gui.window.image_canvas[0][0]["ax"]
        assert list(ax.get_xticks()) == [] and ax.get_xlabel() == ""
        assert np.asarray(gui.window.image_canvas[0][0]["data"].get_array()).shape[0] > 20
    finally:
        gui.close()


@pytest.mark.parametrize("extent", [(0, 1, 2), "abc", (0, 1, 2, "x"), (0, 1, True, 3)])
def test_bad_extent_raises_type_error(extent):
    @interactive()
    def bad():
        layout.style("out", extent=extent)
        return MAP.copy()

    def p():
        out = bad()
        return out

    with pytest.raises(FilterError) as exc_info:
        HeadlessPipeline.from_function(p)()
    assert isinstance(exc_info.value.original_error, TypeError)
    assert "(x0, x1, y0, y1)" in str(exc_info.value.original_error)


def test_xlabel_with_descenders_is_not_clipped():
    shown = apply_display_style(np.zeros((97, 370)), {"colormap": "gray", "vmin": -1, "vmax": 1, "xlabel": "time (s)"})
    bottom_rows = shown[-3:]
    assert bottom_rows.min() > 0.9  # white below the label: nothing cut at the edge
    label_rows = shown[-(shown.shape[0] - 97 * 3) :]
    assert label_rows.min() < 0.3  # the label is drawn
