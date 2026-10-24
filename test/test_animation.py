"""Animation export: render a TimeControl-driven pipeline to a GIF / PNG frames."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image as PILImage

from interactive_pipe import TimeControl, export_animation, interactive
from interactive_pipe.data_objects.curves import Curve
from interactive_pipe.graphical.actions import DEFAULT_ACTIONS
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.pipeline import HeadlessPipeline

HEIGHT, WIDTH = 8, 12


@interactive(time=TimeControl(update_interval_ms=50))
def anim_gradient(time=0.0):
    """Horizontal gradient scrolling with time (grayscale)."""
    x = np.linspace(0.0, 1.0, WIDTH)[None, :]
    return np.repeat((x + time) % 1.0, HEIGHT, axis=0)


@interactive(gain=(0.5, [0.0, 1.0]))
def anim_color(img, gain=0.5):
    return np.stack([img, img * gain, 1.0 - img], axis=-1)


@interactive(time=TimeControl(name="other_time", update_interval_ms=50))
def anim_second_clock(img, time=0.0):
    return img


def anim_curve(img):
    return Curve([[np.arange(3), np.arange(3)]])


@interactive(gain=(0.5, [0.0, 1.0]))
def anim_static(gain=0.5):
    return np.full((HEIGHT, WIDTH), gain)


def anim_pipeline():
    gray = anim_gradient()
    color = anim_color(gray)
    return gray, color


def anim_grid_pipeline():
    gray = anim_gradient()
    color = anim_color(gray)
    return [[gray, color], [color]]


def anim_two_clocks_pipeline():
    gray = anim_gradient()
    other = anim_second_clock(gray)
    return gray, other


def anim_curve_pipeline():
    gray = anim_gradient()
    curve = anim_curve(gray)
    return curve, gray


def anim_static_pipeline():
    img = anim_static()
    return img


def build(func):
    pipeline = HeadlessPipeline.from_function(func, cache=False)
    pipeline.inputs = []  # no pipeline inputs: the frames come from the time control
    return pipeline


def build_grid():
    pipeline = build(anim_grid_pipeline)
    pipeline.outputs = [["gray", None], [None, "color"]]  # None placeholders: empty cells
    return pipeline


def time_ctrl(pipeline):
    return next(ctrl for ctrl in pipeline.controls if isinstance(ctrl, TimeControl))


def test_gif_has_expected_frames_size_and_motion(tmp_path):
    pipeline = build(anim_pipeline)
    path = export_animation(pipeline, tmp_path / "anim.gif", duration=1.0, fps=8)
    assert path == tmp_path / "anim.gif"
    with PILImage.open(path) as gif:
        assert gif.n_frames == 8
        assert gif.size == (WIDTH, HEIGHT)
        frames = []
        for k in range(gif.n_frames):
            gif.seek(k)
            frames.append(np.asarray(gif.convert("RGB")))
    assert not np.array_equal(frames[0], frames[3])
    assert frames[0].shape == (HEIGHT, WIDTH, 3)


def test_png_sequence_in_directory_and_by_stem(tmp_path):
    pipeline = build(anim_pipeline)
    folder = tmp_path / "frames"
    folder.mkdir()
    assert export_animation(pipeline, folder, duration=0.5, fps=10, output=1) == folder
    written = sorted(p.name for p in folder.iterdir())
    assert written == [f"frames_{k:04d}.png" for k in range(5)]
    with PILImage.open(folder / "frames_0000.png") as first:
        assert first.mode == "RGB"
        assert first.size == (WIDTH, HEIGHT)

    assert export_animation(pipeline, tmp_path / "shot.png", duration=0.3, fps=10) == tmp_path
    assert sorted(p.name for p in tmp_path.glob("shot_*.png")) == ["shot_0000.png", "shot_0001.png", "shot_0002.png"]


def test_output_cell_of_a_2d_layout(tmp_path):
    pipeline = build_grid()
    folder = export_animation(pipeline, tmp_path / "grid", duration=0.2, fps=10, output=(1, 1))
    frame = np.asarray(PILImage.open(folder / "grid_0000.png"))
    # anim_color: blue channel = 1 - gray, so not a grayscale frame
    assert not np.array_equal(frame[..., 0], frame[..., 2])
    with pytest.raises(ValueError, match="empty"):
        export_animation(pipeline, tmp_path / "empty.gif", duration=0.2, fps=10, output=(0, 1))


def test_default_output_is_first_non_empty_grid_cell(tmp_path):
    pipeline = build_grid()
    folder = export_animation(pipeline, tmp_path / "g", duration=0.1, fps=10)
    frame = np.asarray(PILImage.open(folder / "g_0000.png"))
    assert np.array_equal(frame[..., 0], frame[..., 2])  # grayscale cell (0, 0)


def test_no_time_control_raises(tmp_path):
    pipeline = build(anim_static_pipeline)
    with pytest.raises(ValueError, match="No TimeControl in this pipeline"):
        export_animation(pipeline, tmp_path / "x.gif")
    assert not (tmp_path / "x.gif").exists()


def test_several_time_controls_need_a_name(tmp_path):
    pipeline = build(anim_two_clocks_pipeline)
    with pytest.raises(ValueError, match="Several TimeControls"):
        export_animation(pipeline, tmp_path / "x.gif", duration=0.1)
    path = export_animation(pipeline, tmp_path / "x.gif", duration=0.2, fps=10, time_control="other_time")
    assert path.exists()
    with pytest.raises(ValueError, match="No TimeControl named"):
        export_animation(pipeline, tmp_path / "y.gif", duration=0.1, time_control="missing")


def test_non_image_output_raises_type_error(tmp_path):
    pipeline = build(anim_curve_pipeline)
    with pytest.raises(TypeError, match="image outputs"):
        export_animation(pipeline, tmp_path / "c.gif", duration=0.1, fps=10)
    # selecting the image output works
    assert export_animation(pipeline, tmp_path / "c.gif", duration=0.1, fps=10, output=1).exists()


@pytest.mark.parametrize(
    "kwargs",
    [dict(fps=0), dict(duration=-1.0), dict(duration=0.01, fps=10), dict(loop=-1)],
)
def test_invalid_arguments(tmp_path, kwargs):
    with pytest.raises(ValueError):
        export_animation(build(anim_pipeline), tmp_path / "a.gif", **kwargs)


def test_unsupported_suffix(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        export_animation(build(anim_pipeline), tmp_path / "a.mp4", duration=0.1)


def test_control_value_and_results_are_restored(tmp_path):
    pipeline = build(anim_pipeline)
    ctrl = time_ctrl(pipeline)
    ctrl.value = 0.25
    before = pipeline.run()
    export_animation(pipeline, tmp_path / "a.gif", duration=1.0, fps=5)
    assert ctrl.value == 0.25
    assert pipeline.parameters["anim_gradient"]["time"] == 0.25
    np.testing.assert_array_equal(pipeline.results[0], before[0])


# ---------------------------------------------------------------------
# GUI action


class RecordingGUI(InteractivePipeGUI):
    """Backend-free GUI recording messages and resync calls."""

    def init_app(self, **kwargs):
        self.messages = []
        self.resynced = 0
        self.set_default_key_bindings()

    def print_message(self, message_list):
        self.messages.append(message_list)

    def on_parameters_loaded(self):
        self.resynced += 1


def build_gui(func):
    return RecordingGUI(pipeline=build(func), name="anim gui")


def test_action_is_registered_on_v():
    action = next(a for a in DEFAULT_ACTIONS if a.name == "export_animation")
    assert (action.key, action.menu, action.method) == ("v", "Pipeline", "export_animation")
    gui = build_gui(anim_pipeline)
    assert gui.key_bindings["v"] == gui.export_animation


def test_gui_action_writes_the_gif(tmp_path, monkeypatch):
    gui = build_gui(anim_pipeline)
    target = tmp_path / "out.gif"
    asked = {}

    def fake_ask(title, save, extensions, default_name):
        asked.update(title=title, save=save, extensions=extensions, default_name=default_name)
        return target

    monkeypatch.setattr(gui, "ask_path", fake_ask)
    gui.export_animation()
    assert asked == dict(title="Export animation", save=True, extensions=[".gif", ".png"], default_name="anim_gui.gif")
    with PILImage.open(target) as gif:
        assert gif.n_frames == 50  # defaults: 5 s at 10 fps
    assert gui.resynced == 1
    assert any(str(target) in " ".join(lines) for lines in gui.messages)


def test_gui_action_cancelled_writes_nothing(tmp_path, monkeypatch):
    gui = build_gui(anim_pipeline)
    monkeypatch.setattr(gui, "ask_path", lambda *args: None)
    gui.export_animation()
    assert list(tmp_path.iterdir()) == []
    assert gui.messages == []


def test_gui_action_without_time_control_reports_and_does_not_raise(tmp_path, monkeypatch):
    gui = build_gui(anim_static_pipeline)
    monkeypatch.setattr(gui, "ask_path", lambda *args: tmp_path / "x.gif")
    gui.export_animation()
    assert not (tmp_path / "x.gif").exists()
    assert any("No TimeControl in this pipeline" in " ".join(lines) for lines in gui.messages)


def test_gui_action_reports_export_errors(tmp_path, monkeypatch):
    gui = build_gui(anim_curve_pipeline)
    monkeypatch.setattr(gui, "ask_path", lambda *args: tmp_path / "x.gif")
    gui.export_animation()
    assert any("image outputs" in " ".join(lines) for lines in gui.messages)


def test_mpl_backend_action_writes_the_gif(tmp_path, monkeypatch):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    mpl_gui = pytest.importorskip("interactive_pipe.graphical.mpl_gui")
    gui = mpl_gui.InteractivePipeMatplotlib(pipeline=build(anim_pipeline), name="mpl anim")
    gui.window.refresh()
    ctrl = time_ctrl(gui.pipeline)
    ctrl.value = 1.5
    messages = []
    monkeypatch.setattr(gui, "print_message", messages.append)
    monkeypatch.setattr(gui, "ask_path", lambda *args: tmp_path / "mpl.gif")
    gui.key_bindings["v"]()
    with PILImage.open(tmp_path / "mpl.gif") as gif:
        assert gif.n_frames == 50
    assert ctrl.value == 1.5
    assert messages and "Animation exported" in messages[-1][0]
