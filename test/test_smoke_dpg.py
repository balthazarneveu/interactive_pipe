"""Dear PyGui backend smoke tests (no viewport).

Dear PyGui builds its widget tree inside a context without opening a window,
so everything up to (not including) ``run()`` is exercised here: window
build, the layout.style -> framework_state -> title chain, per-type parameter
updates through the widget callbacks, panels/collapsible/detached windows,
every update_image branch, cell rebuilds on output type change, key dispatch,
timers and the layout math.

Skipped entirely when dearpygui is not installed. Never call
``render_dearpygui_frame`` here: it segfaults without a viewport.
"""

import logging

import numpy as np
import pytest

dpg_gui = pytest.importorskip("interactive_pipe.graphical.dpg_gui")

from interactive_pipe import Backend, events, interactive, layout  # noqa: E402
from interactive_pipe.data_objects.curves import Curve, SingleCurve  # noqa: E402
from interactive_pipe.data_objects.image import Image  # noqa: E402
from interactive_pipe.data_objects.table import Table  # noqa: E402
from interactive_pipe.graphical import dpg_backend, dpg_control  # noqa: E402
from interactive_pipe.graphical.dpg_panels import DpgTimer  # noqa: E402
from interactive_pipe.headless.control import CircularControl, Control, TextPrompt, TimeControl  # noqa: E402
from interactive_pipe.headless.keyboard import KeyboardControl  # noqa: E402
from interactive_pipe.headless.panel import Panel  # noqa: E402
from interactive_pipe.headless.pipeline import HeadlessPipeline  # noqa: E402
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class  # noqa: E402

dpg = dpg_backend.dpg
InteractivePipeDPG = dpg_gui.InteractivePipeDPG

INPUT_IMAGE = np.linspace(0.0, 1.0, 4 * 4, dtype=np.float64).reshape(4, 4)


@pytest.fixture(autouse=True)
def _fresh_dpg_context():
    yield
    dpg_backend.destroy_context()


# ---------------------------------------------------------------------------
# Module-level filters & pipelines (the AST parser reads pipeline source)
# ---------------------------------------------------------------------------
@interactive(
    brightness=(0.5, [0.0, 1.0]),
    inverted=Control(False),
    mode=("mean", ["mean", "max"]),
    steps=(2, [0, 4]),
)
def adjust(img, brightness=0.5, inverted=False, mode="mean", steps=2):
    layout.style("adjusted", title=f"mode={mode}")
    out = img * brightness
    return 1.0 - out if inverted else out


@interactive()
def to_rgb(img):
    return np.stack([img, img, img], axis=-1)


def basic_pipeline(img):
    adjusted = adjust(img)
    rgb = to_rgb(img)
    return adjusted, rgb


@interactive(ncurves=(1, [1, 3]))
def make_curve(img, ncurves=1):
    curves = [SingleCurve(y=img.mean(axis=0) * (k + 1), style="r-", label=f"c{k}") for k in range(ncurves)]
    curves.append(SingleCurve(y=img.max(axis=0), style="k."))  # marker only -> scatter series
    return Curve(curves, ylabel="mean", xlim=(0, 3))


@interactive()
def make_table(img):
    return Table(img[:2, :2], columns=["a", "b"], title="stats")


@interactive()
def make_text(img):
    return f"mean={img.mean():.2f}"


def mixed_pipeline(img):
    gray = adjust(img)
    curve = make_curve(img)
    tab = make_table(img)
    txt = make_text(img)
    return [[gray, curve], [tab, txt]]


@interactive()
def make_signal(img):
    return img.flatten()


def signal_pipeline(img):
    signal = make_signal(img)
    return signal


TOP_PANEL = Panel("TopTools", position="top")
LEFT_PANEL = Panel("LeftTools", position="left")
COLLAPSIBLE_PANEL = Panel("Extras", collapsible=True, collapsed=True)
GRID_PANEL = Panel("Grid", position="right").add_elements([[Panel("GA"), Panel("GB")]])
GRID_SUB_A, GRID_SUB_B = GRID_PANEL.elements[0]


@interactive(
    top_gain=Control(0.5, [0.0, 1.0], group=TOP_PANEL),
    left_gain=Control(0.5, [0.0, 1.0], group=LEFT_PANEL),
    extra_gain=Control(0.5, [0.0, 1.0], group=COLLAPSIBLE_PANEL),
    grid_a=Control(0.5, [0.0, 1.0], group=GRID_SUB_A),
    grid_b=Control(True, group=GRID_SUB_B),
)
def panel_filter(img, top_gain=0.5, left_gain=0.5, extra_gain=0.5, grid_a=0.5, grid_b=True):
    return img * top_gain * left_gain * extra_gain * grid_a


def panel_pipeline(img):
    out = panel_filter(img)
    return out


DETACHED_PANEL = Panel("DetachedTools", detached=True, detached_size=(300, 200))


@interactive(detached_gain=Control(0.5, [0.0, 1.0], group=DETACHED_PANEL))
def detached_filter(img, detached_gain=0.5):
    return img * detached_gain


def detached_pipeline(img):
    out = detached_filter(img)
    return out


EVENT_LOG = []


@interactive()
def event_probe(img):
    EVENT_LOG.append(events.get("noise_evt"))
    return img


def event_pipeline(img):
    out = event_probe(img)
    return out


@interactive(
    free_int=Control(3), free_float=Control(0.5), angle=CircularControl(90.0, [0.0, 360.0]), txt=TextPrompt("hi")
)
def free_filter(img, free_int=3, free_float=0.5, angle=90.0, txt="hi"):
    layout.style("out", title=txt)
    return img * free_float + free_int + angle


def free_pipeline(img):
    out = free_filter(img)
    return out


@interactive(out_kind=("image", ["image", "text", "curve", "table", "signal"]))
def shape_shifter(img, out_kind="image"):
    if out_kind == "text":
        return "hello"
    if out_kind == "curve":
        return Curve([SingleCurve(y=img.mean(axis=0))])
    if out_kind == "table":
        return Table(img[:2, :2], columns=["a", "b"])
    if out_kind == "signal":
        return img.flatten()
    return img


def shape_shifter_pipeline(img):
    out = shape_shifter(img)
    return out


@interactive(grid=("row", ["row", "square"]))
def grid_switch(img, grid="row"):
    if grid == "square":
        layout.grid([["a", "b"], ["c", "d"]])
    else:
        layout.grid([["a", "b", "c", "d"]])
    return img


def grid_pipeline(img):
    a = grid_switch(img)
    b = to_rgb(img)
    c = to_rgb(img)
    d = to_rgb(img)
    return [[a, b, c, d]]


@interactive(level=KeyboardControl(1, [0, 3], keydown="j", keyup="k"), big=(False, None, "big"))
def keyboard_filter(img, level=1, big=False):
    layout.style("out", title=f"level={level}")
    return img * level


def keyboard_pipeline(img):
    out = keyboard_filter(img)
    return out


@interactive(t=TimeControl(update_interval_ms=10, pause_resume_key="p"))
def timed_filter(img, t=0.0):
    layout.style("out", title=f"t={t:.0f}")
    return img


def time_pipeline(img):
    out = timed_filter(img)
    return out


def build_gui(pipeline_function, **gui_kwargs):
    pipeline = HeadlessPipeline.from_function(pipeline_function, inputs=["img"])
    gui = InteractivePipeDPG(pipeline=pipeline, name="smoke", **gui_kwargs)
    gui.pipeline.inputs = [INPUT_IMAGE.copy()]
    return gui


def cell_children(window, row, col):
    return dpg.get_item_children(window.image_canvas[row][col]["cell"], 1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_backend_registered_and_selectable():
    assert Backend.DPG == "dpg"
    assert get_interactive_pipeline_class("dpg") is InteractivePipeDPG
    assert get_interactive_pipeline_class(Backend.DPG) is InteractivePipeDPG


def test_window_builds_and_refreshes_with_styled_title():
    gui = build_gui(basic_pipeline, size=(640, 480))
    assert dpg_backend.context_alive()
    gui.window.refresh()
    canvas = gui.window.image_canvas
    assert len(canvas) == 1 and len(canvas[0]) == 2
    cell = canvas[0][0]
    assert cell["kind"] == "image" and cell["natural_size"] == (4, 4)
    assert dpg.does_item_exist(cell["texture"]) and dpg.does_item_exist(cell["content"])
    assert cell["buffer"].shape == (4, 4, 4) and cell["buffer"].dtype == np.float32
    # layout.style -> framework_state.output_styles -> get_current_style
    assert dpg.get_value(cell["title"]) == "mode=mean"
    assert dpg.get_value(canvas[0][1]["title"]) == "rgb"  # unstyled output falls back to its name
    assert gui.window.viewport_size == (640, 480)


def test_second_refresh_reuses_the_texture_buffer():
    gui = build_gui(basic_pipeline)
    window = gui.window
    window.refresh()
    cell = window.image_canvas[0][0]
    texture, buffer = cell["texture"], cell["buffer"]
    window.update_parameter("brightness", 1.0)
    assert cell["texture"] == texture and cell["buffer"] is buffer  # same size: pixels copied in place
    assert buffer[..., 0].max() == pytest.approx(1.0)
    assert buffer[..., 3].min() == 1.0


def test_update_parameter_per_control_type_through_widget_callbacks():
    gui = build_gui(basic_pipeline)
    window = gui.window
    widgets = window.widget_list
    assert isinstance(widgets["brightness"], dpg_control.FloatSliderControl)
    assert isinstance(widgets["steps"], dpg_control.IntSliderControl)
    assert isinstance(widgets["inverted"], dpg_control.TickBoxControl)
    assert isinstance(widgets["mode"], dpg_control.DropdownMenuControl)
    # widgets hand the window values in the control's own domain
    widgets["brightness"]._on_change(None, 0.3333, None)  # snapped on the step grid (range / 100)
    assert window.ctrl["brightness"].value == pytest.approx(0.33)
    assert dpg.get_value(widgets["brightness"].control_widget) == pytest.approx(0.33, abs=1e-6)
    widgets["mode"]._emit("max")
    assert window.ctrl["mode"].value == "max"
    widgets["inverted"]._emit(True)
    assert window.ctrl["inverted"].value is True
    widgets["steps"]._on_change(None, 3, None)
    assert window.ctrl["steps"].value == 3
    # the refresh triggered by updates must propagate to the styled title
    assert dpg.get_value(window.image_canvas[0][0]["title"]) == "mode=max"
    assert gui.pipeline.parameters["adjust"]["mode"] == "max"


def test_reset_parameters_restores_controls_and_widgets():
    gui = build_gui(basic_pipeline)
    window = gui.window
    window.update_parameter("brightness", 1.0)
    window.update_parameter("mode", "max")
    gui.reset_parameters()
    assert window.ctrl["brightness"].value == 0.5 and window.ctrl["mode"].value == "mean"
    assert dpg.get_value(window.widget_list["brightness"].control_widget) == pytest.approx(0.5)
    assert dpg.get_value(window.widget_list["mode"].control_widget) == "mean"
    assert dpg.get_value(window.image_canvas[0][0]["title"]) == "mode=mean"


def test_panels_by_position_grid_rows_and_collapsible_header():
    gui = build_gui(panel_pipeline)
    window = gui.window
    assert len(dpg.get_item_children(window.top_container, 1)) == 1
    assert len(dpg.get_item_children(window.left_container, 1)) == 1
    assert len(dpg.get_item_children(window.right_container, 1)) == 1
    assert dpg.get_item_configuration(window.left_container)["width"] == dpg_gui.SIDE_PANEL_WIDTH
    bottom_children = dpg.get_item_children(window.bottom_container, 1)
    assert len(bottom_children) == 1  # collapsible defaults to bottom
    header = bottom_children[0]
    assert dpg.get_item_type(header).endswith("mvCollapsingHeader")
    assert dpg.get_item_configuration(header)["label"] == "Extras"
    assert dpg.get_value(header) is False  # starts collapsed
    # grid panel: one horizontal row holding the two sub panels
    right_panel = dpg.get_item_children(window.right_container, 1)[0]
    row_groups = [item for item in dpg.get_item_children(right_panel, 1) if dpg.get_item_type(item).endswith("mvGroup")]
    assert len(row_groups) == 1 and dpg.get_item_configuration(row_groups[0])["horizontal"] is True
    slots = dpg.get_item_children(row_groups[0], 1)
    assert len(slots) == 2 and len(window.sized_items) == 2
    # grid cells share the side panel width and follow relayout
    expected_width = window.sized_items[0][1]()
    assert dpg.get_item_configuration(slots[0])["width"] == expected_width
    assert 80 <= expected_width < dpg_gui.SIDE_PANEL_WIDTH // 2
    window.refresh()
    window.relayout()
    assert dpg.get_item_configuration(slots[1])["width"] == expected_width
    assert set(window.widget_list) == {"top_gain", "left_gain", "extra_gain", "grid_a", "grid_b"}


def test_detached_panel_window_lifecycle():
    gui = build_gui(detached_pipeline)
    window = gui.window
    assert len(window.detached_windows) == 1
    detached = window.detached_windows[0]
    assert dpg.get_item_configuration(detached)["label"] == "DetachedTools"
    assert dpg.get_item_configuration(detached)["width"] == 300
    assert "detached_gain" in window.widget_list
    window.on_detached_closed(detached)
    assert window.detached_windows == []


def test_update_image_all_branches_create_and_update():
    gui = build_gui(mixed_pipeline)
    window = gui.window
    window.refresh()  # first pass: create plot/table/text items
    canvas = window.image_canvas
    plot_state = canvas[0][1]["plot"]
    series_before = [entry["item"] for entry in plot_state["series"]]
    assert [entry["scatter"] for entry in plot_state["series"]] == [False, True]
    assert dpg.get_item_configuration(plot_state["y_axis"])["label"] == "mean"
    window.refresh()  # second pass: update path for Curve/Table/Text
    assert [entry["item"] for entry in plot_state["series"]] == series_before
    assert canvas[0][0]["kind"] == "image" and canvas[1][0]["kind"] == "table" and canvas[1][1]["kind"] == "text"
    assert dpg.get_value(canvas[1][1]["content"]).startswith("mean=")
    table_children = dpg.get_item_children(canvas[1][0]["content"], 1)
    assert dpg.get_value(table_children[0]) == "stats"  # table title
    table_item = table_children[1]
    assert len(dpg.get_item_children(table_item, 0)) == 2  # columns
    assert len(dpg.get_item_children(table_item, 1)) == 2  # rows
    # series count follows the Curve between frames
    window.update_parameter("ncurves", 3)
    assert len(plot_state["series"]) == 4
    window.update_parameter("ncurves", 1)
    assert len(plot_state["series"]) == 2
    assert all(dpg.does_item_exist(entry["item"]) for entry in plot_state["series"])


def test_1d_output_displays_as_curve_fallback(caplog):
    gui = build_gui(signal_pipeline)
    with caplog.at_level(logging.WARNING):
        gui.window.refresh()
    cell = gui.window.image_canvas[0][0]
    assert cell["kind"] == "curve" and cell["plot"] is not None
    assert "not supported by the dpg backend" in caplog.text


def test_output_type_change_between_frames_rebuilds_the_cell():
    gui = build_gui(shape_shifter_pipeline)
    window = gui.window
    window.refresh()
    for kind in ["text", "curve", "table", "image", "signal", "text", "image", "curve", "text"]:
        window.update_parameter("out_kind", kind)
        cell = window.image_canvas[0][0]
        expected_kind = "curve" if kind == "signal" else kind
        assert cell["kind"] == expected_kind
        # the cell group holds exactly the title and one content item
        children = cell_children(window, 0, 0)
        assert children == [cell["title"], cell["content"]]
        assert (cell["texture"] is not None) == (expected_kind == "image")
    assert dpg.get_value(window.image_canvas[0][0]["content"]) == "hello"


def test_layout_grid_change_rebuilds_rows():
    gui = build_gui(grid_pipeline)
    window = gui.window
    window.refresh()
    assert (len(window.image_canvas), len(window.image_canvas[0])) == (1, 4)
    assert len(window._rows) == 1
    first_row_group = window._rows[0]["group"]
    window.update_parameter("grid", "square")
    assert (len(window.image_canvas), len(window.image_canvas[0])) == (2, 2)
    assert len(window._rows) == 2 and not dpg.does_item_exist(first_row_group)
    assert len(dpg.get_item_children(window.image_grid, 1)) == 4  # 2 rows + 2 spacers
    window.update_parameter("grid", "row")
    assert (len(window.image_canvas), len(window.image_canvas[0])) == (1, 4)


def test_relayout_fits_grid_in_client_area_with_uniform_scale():
    gui = build_gui(basic_pipeline, size=(800, 600))
    window = gui.window
    assert window.left_container is None and window.right_container is None  # no side panels
    window.refresh()
    window.on_viewport_resize(None, [800, 600, 800, 560])
    col_widths, row_heights = window.natural_grid_size()
    assert col_widths == [4, 4] and row_heights == [4 + dpg_gui.TITLE_HEIGHT]
    assert window.scale_factor > 1.0  # tiny images are scaled up to fill the window
    for cell in window.image_canvas[0]:
        config = dpg.get_item_configuration(cell["content"])
        assert config["width"] == int(4 * window.scale_factor)
        assert config["height"] == int(4 * window.scale_factor)
        assert config["width"] <= 800
    assert dpg.get_item_configuration(window._rows[0]["spacer"])["width"] >= 0
    assert dpg.get_item_configuration(window.grid_container)["height"] <= 560
    assert dpg.get_item_configuration(window.grid_container)["width"] == 800 - dpg_gui.LAYOUT_MARGIN


def test_relayout_reserves_side_panel_columns():
    gui = build_gui(panel_pipeline, size=(1000, 700))
    window = gui.window
    window.refresh()
    window.on_viewport_resize(None, [1000, 700, 1000, 660])
    reserved = 2 * (dpg_gui.SIDE_PANEL_WIDTH + dpg_gui.SIDE_PANEL_GAP) + dpg_gui.LAYOUT_MARGIN
    assert dpg.get_item_configuration(window.grid_container)["width"] == 1000 - reserved
    grid_height = dpg.get_item_configuration(window.grid_container)["height"]
    assert dpg.get_item_configuration(window.left_container)["height"] == grid_height


def test_key_press_dispatch_and_keyboard_control():
    gui = build_gui(keyboard_pipeline)
    window = gui.window
    window.refresh()
    assert "level" not in window.widget_list  # keyboard controls have no widget
    gui._on_key_press(None, dpg.mvKey_K, None)
    assert window.ctrl["level"].value == 2
    assert dpg.get_value(window.image_canvas[0][0]["title"]) == "level=2"
    gui._on_key_press(None, dpg.mvKey_J, None)
    gui._on_key_press(None, dpg.mvKey_J, None)
    assert window.ctrl["level"].value == 0  # saturates at the range bound
    gui._on_key_press(None, 999999, None)  # unknown key code: ignored
    window.update_parameter("big", True)
    gui._on_key_press(None, dpg.mvKey_R, None)  # "r" resets everything
    assert window.ctrl["level"].value == 1 and window.ctrl["big"].value is False
    help_lines = gui.show_help()
    assert any(line.startswith("[j]/[k]") for line in help_lines)
    assert dpg.does_item_exist(window._message_window)


def test_key_presses_are_muted_while_typing_in_a_prompt(monkeypatch):
    gui = build_gui(free_pipeline)
    window = gui.window
    window.refresh()
    assert window.prompt_widgets  # text entry + numeric inputs take focus
    monkeypatch.setattr(window, "text_entry_focused", lambda: True)
    window.update_parameter("free_int", 9)
    gui._on_key_press(None, dpg.mvKey_R, None)
    assert window.ctrl["free_int"].value == 9  # reset was not triggered


def test_context_key_event_lifecycle():
    gui = build_gui(basic_pipeline)
    gui.bind_key_to_context("n", "noise_evt", "toggle noise event")
    assert gui.pipeline.framework_state.events["noise_evt"] is False
    observed = {}

    def spy_refresh():
        observed["during_press"] = gui.pipeline.framework_state.events["noise_evt"]

    gui.on_press("n", refresh_func=spy_refresh)
    assert observed["during_press"] is True
    assert gui.pipeline.framework_state.events["noise_evt"] is False


def test_context_key_event_visible_to_filter_through_events_proxy():
    EVENT_LOG.clear()
    gui = build_gui(event_pipeline)
    gui.bind_key_to_context("n", "noise_evt", "toggle noise event")
    gui.pipeline.run()
    gui._on_key_press(None, dpg.mvKey_N, None)
    gui.pipeline.reset_cache()
    gui.pipeline.run()
    assert EVENT_LOG == [False, True, False]


def test_load_parameters_syncs_controls_and_widgets(tmp_path, monkeypatch):
    from interactive_pipe.data_objects.parameters import Parameters

    gui = build_gui(basic_pipeline)
    gui.window.refresh()
    tuning_path = tmp_path / "tuning.yaml"
    gui.pipeline.export_tuning(tuning_path)
    saved = Parameters.from_file(tuning_path).data
    saved["adjust"]["brightness"] = 0.25
    saved["adjust"]["mode"] = "max"
    Parameters(saved).save(tuning_path, override=True)
    monkeypatch.setattr(Parameters, "prompt_file", staticmethod(lambda *_a, **_k: str(tuning_path)))
    gui.load_parameters()
    assert gui.window.ctrl["brightness"].value == pytest.approx(0.25)
    assert gui.window.ctrl["mode"].value == "max"
    assert dpg.get_value(gui.window.widget_list["mode"].control_widget) == "max"
    assert dpg.get_value(gui.window.widget_list["brightness"].control_widget) == pytest.approx(0.25)
    assert dpg.get_value(gui.window.image_canvas[0][0]["title"]) == "mode=max"


def test_rangeless_knob_and_prompt_controls():
    gui = build_gui(free_pipeline)
    window = gui.window
    window.refresh()
    widgets = window.widget_list
    assert isinstance(widgets["free_int"], dpg_control.IntInputControl)
    assert isinstance(widgets["free_float"], dpg_control.FloatInputControl)
    assert isinstance(widgets["angle"], dpg_control.KnobControl)
    assert isinstance(widgets["txt"], dpg_control.PromptControl)
    widgets["free_int"]._on_change(None, 7, None)
    widgets["free_float"]._on_change(None, 2.25, None)
    widgets["angle"]._on_change(None, 180.0, None)
    widgets["txt"]._emit("typed")
    assert window.ctrl["free_int"].value == 7 and window.ctrl["free_float"].value == pytest.approx(2.25)
    assert window.ctrl["angle"].value == pytest.approx(180.0)
    assert dpg.get_value(window.image_canvas[0][0]["title"]) == "typed"
    assert gui.pipeline.parameters["free_filter"]["free_int"] == 7
    gui.reset_parameters()
    assert dpg.get_value(widgets["free_int"].control_widget) == 3
    assert dpg.get_value(widgets["free_float"].control_widget) == pytest.approx(0.5)
    assert dpg.get_value(widgets["angle"].control_widget) == pytest.approx(90.0)
    assert dpg.get_value(widgets["txt"].control_widget) == "hi"


def test_icon_buttons_show_and_reset_selection(tmp_path):
    dpg_backend.create_context()
    registry = dpg.add_texture_registry()
    icons = []
    for name, level in (("a", 0.2), ("b", 0.8)):
        icon_path = tmp_path / f"{name}.png"
        Image(np.full((8, 8, 3), level, dtype=np.float32)).save(icon_path)
        icons.append(icon_path)
    ctrl = Control("a", ["a", "b"], icons=icons, name="icon_ctrl")
    received = []
    widget = dpg_control.ControlFactory(texture_registry=registry).create_control(
        ctrl, lambda name, value: received.append((name, value))
    )
    assert isinstance(widget, dpg_control.IconButtonsControl)
    with dpg.window() as window:
        widget.create(window)
    assert len(widget.control_widgets) == 2 and widget.selected_choice() == "a"
    widget._on_click(widget.control_widgets[1], None, "b")
    assert received == [("icon_ctrl", "b")]
    assert widget.selected_choice() == "b"
    ctrl.value = "a"
    widget.reset()
    assert widget.selected_choice() == "a"


def test_single_choice_dropdown_has_no_widget():
    dpg_backend.create_context()
    ctrl = Control("only", ["only"], name="single")
    assert dpg_control.ControlFactory().create_control(ctrl, lambda *_a: None) is None


def test_time_control_timer_ticks_and_pauses():
    gui = build_gui(time_pipeline)
    window = gui.window
    window.refresh()
    assert "t" not in window.widget_list  # driven by the timer, no slider
    assert window.timer is not None and window.timer.running and window.timers == [window.timer]
    gui.start_time -= 5.0  # pretend 5 seconds elapsed
    window.timer.start(now=0.0)
    assert window.timer.tick(0.005) is False  # 10 ms interval not reached
    assert window.timer.tick(0.02) is True
    assert window.ctrl["t"].value >= 5.0
    assert dpg.get_value(window.image_canvas[0][0]["title"]).startswith("t=")
    gui._on_key_press(None, dpg.mvKey_P, None)  # pause
    assert window.timer.running is False
    gui._on_key_press(None, dpg.mvKey_P, None)  # resume
    assert window.timer.running is True


def test_dpg_timer_standalone():
    fired = []
    timer = DpgTimer(100, lambda: fired.append(1))
    assert timer.tick(10.0) is False  # not started
    timer.start(now=10.0)
    assert timer.tick(10.05) is False and timer.tick(10.1) is True and timer.tick(10.15) is False
    timer.stop()
    assert timer.tick(20.0) is False


def test_show_message_lists_lines_in_a_modal_window():
    gui = build_gui(basic_pipeline)
    gui.print_message(["first line", "second line"])
    window_item = gui.window._message_window
    assert dpg.get_item_configuration(window_item)["modal"] is True
    texts = [dpg.get_value(item) for item in dpg.get_item_children(window_item, 1)[:2]]
    assert texts == ["first line", "second line"]
    gui.print_message(["again"])  # replaces the previous popup
    assert not dpg.does_item_exist(window_item)


def test_audio_flag_only_warns(caplog):
    with caplog.at_level(logging.WARNING):
        gui = build_gui(basic_pipeline, audio=True)
    assert "Audio playback is not supported" in caplog.text
    assert callable(gui.pipeline.framework_state.audio.play)


def test_close_before_run_destroys_context():
    gui = build_gui(basic_pipeline)
    assert dpg_backend.context_alive()
    gui.close()
    assert not dpg_backend.context_alive()


def test_close_and_full_screen_after_run_do_not_touch_a_dead_context(monkeypatch):
    gui = build_gui(basic_pipeline)
    stopped = []
    toggled = []
    monkeypatch.setattr(dpg, "stop_dearpygui", lambda: stopped.append(True))
    monkeypatch.setattr(dpg, "toggle_viewport_fullscreen", lambda: toggled.append(True))
    # state left by run() once the render loop exits: viewport was shown, context destroyed
    gui._viewport_shown = True
    dpg_backend.destroy_context()
    gui.close()  # e.g. from custom_end or caller cleanup
    gui.toggle_full_screen()
    assert stopped == [] and toggled == []
    assert not dpg_backend.context_alive()


class _TickError(RuntimeError):
    pass


def test_run_tears_down_the_context_when_a_timer_tick_raises(monkeypatch):
    gui = build_gui(basic_pipeline)
    # no display here: stub the viewport calls, keep the real widget tree
    for name in ("create_viewport", "set_viewport_resize_callback", "setup_dearpygui", "show_viewport"):
        monkeypatch.setattr(dpg, name, lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dpg, "set_frame_callback", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dpg, "is_dearpygui_running", lambda: True)
    monkeypatch.setattr(dpg, "render_dearpygui_frame", lambda: None)
    monkeypatch.setattr(dpg, "get_viewport_client_width", lambda: 800)
    monkeypatch.setattr(dpg, "get_viewport_client_height", lambda: 600)
    monkeypatch.setattr(gui, "custom_end", lambda: None)

    def failing_tick():
        raise _TickError("filter failed")

    monkeypatch.setattr(gui.window, "tick_timers", failing_tick)
    with pytest.raises(_TickError):
        gui.run()
    assert not dpg_backend.context_alive()
    assert gui._viewport_shown is False and gui.window.viewport_ready is False
    gui.close()  # no crash on a dead context


def test_window_size_validation():
    with pytest.raises(ValueError):
        build_gui(basic_pipeline, size="tiny")
    dpg_backend.destroy_context()
    gui = build_gui(basic_pipeline, size="fullscreen")
    assert gui.window.viewport_size == dpg_gui.DEFAULT_VIEWPORT_SIZE
    dpg_backend.destroy_context()
    gui = build_gui(basic_pipeline, size=400)
    assert gui.window.viewport_size == (400, 300)


def test_numpy_to_rgba_conversions():
    from interactive_pipe.graphical.dpg_image import numpy_to_rgba

    gray = numpy_to_rgba(np.array([[-0.5, 0.5], [1.5, 2.0]]))
    assert gray.shape == (2, 2, 4) and gray.dtype == np.float32 and gray.flags["C_CONTIGUOUS"]
    assert gray[0, 0, 0] == 0.0 and gray[1, 1, 0] == 1.0 and gray[..., 3].min() == 1.0
    rgb = numpy_to_rgba(np.zeros((2, 3, 3)))
    assert rgb.shape == (2, 3, 4) and rgb[..., 3].min() == 1.0
    rgba = numpy_to_rgba(np.full((2, 3, 4), 0.5))
    assert rgba[..., 3].max() == 0.5
    with pytest.raises(NotImplementedError):
        numpy_to_rgba(np.zeros((2, 3, 5)))
