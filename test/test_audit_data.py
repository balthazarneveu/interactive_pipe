"""Regression tests for defects found by the November 2026 code audit (data objects, drawing, matplotlib)."""

import wave

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image as PilImage  # noqa: E402

from interactive_pipe import draw, sound  # noqa: E402
from interactive_pipe.data_objects.curves import Curve, SingleCurve  # noqa: E402
from interactive_pipe.data_objects.image import Image  # noqa: E402
from interactive_pipe.data_objects.video import Video  # noqa: E402


def test_uint8_image_is_saved_without_wrapping(tmp_path):
    values = np.arange(0, 250, 10, dtype=np.uint8).reshape(5, 5)
    img = np.stack([values] * 3, axis=-1)
    path = tmp_path / "u8.png"
    Image.save_image(img, path, backend="pillow")
    np.testing.assert_array_equal(np.array(PilImage.open(path)), img)


def test_nan_pixels_are_saved_black(tmp_path):
    img = np.full((4, 4, 3), np.nan)
    path = tmp_path / "nan.png"
    with np.errstate(invalid="raise"):
        Image.save_image(img, path, backend="pillow")
    assert np.array(PilImage.open(path)).max() == 0


@pytest.mark.parametrize("mode", ["1", "L", "P"])
def test_pillow_loads_gray_bilevel_and_palette_as_rgb(tmp_path, mode):
    gray = PilImage.fromarray(np.array([[0, 255], [255, 0]], dtype=np.uint8), "L")
    path = tmp_path / f"{mode}.png"
    gray.convert(mode).save(path)
    loaded = Image.load_image(path, backend="pillow")
    assert loaded.shape == (2, 2, 3)
    np.testing.assert_allclose(loaded[..., 0], [[0, 1], [1, 0]])


def test_pillow_loads_16_bit_in_unit_range(tmp_path):
    path = tmp_path / "deep.png"
    PilImage.fromarray(np.array([[0, 65535]], dtype=np.uint16)).save(path)
    loaded = Image.load_image(path, backend="pillow")
    assert loaded.max() == pytest.approx(1.0)


def test_image_extensions_are_case_insensitive(tmp_path):
    for name in ("upper.PNG", "long.jpeg"):
        path = tmp_path / name
        PilImage.new("RGB", (4, 4), (255, 0, 0)).save(path)
        assert Image.from_file(path).data.shape == (4, 4, 3)


def test_opencv_write_failure_raises(tmp_path):
    pytest.importorskip("cv2")
    with pytest.raises(OSError, match="Could not write"):
        Image.save_image_cv2(np.zeros((4, 4, 3)), tmp_path / "missing_folder" / "a.png")


def test_video_from_arrays_leaves_them_writable():
    frames = [np.zeros((4, 4, 3)) for _ in range(3)]
    video = Video(frames)
    video[0]
    assert frames[0].flags.writeable
    assert not video[0].flags.writeable


def test_video_of_a_video_keeps_its_trimming():
    frames = np.arange(30, dtype=np.float64)[:, None, None] * np.ones((1, 2, 2))
    trimmed = Video(frames, start=10)
    again = Video(trimmed)
    assert len(again) == 20
    assert again[0][0, 0] == 10
    assert Video(trimmed, start=5)[0][0, 0] == 15


def test_video_path_with_brackets_is_a_file_when_it_exists(tmp_path):
    folder = tmp_path / "clip[1]"
    folder.mkdir()
    for index in range(2):
        PilImage.new("RGB", (4, 4), (index * 100, 0, 0)).save(folder / f"{index}.png")
    assert len(Video(str(folder))) == 2


def test_sound_load_stereo_resampled_stays_stereo(tmp_path):
    path = tmp_path / "stereo.wav"
    samples = (np.sin(np.linspace(0, 20, 8000))[:, None] * np.array([[1.0, 0.5]]) * 20000).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())
    signal, rate = sound.load(path, mono=False, sample_rate=4000)
    assert rate == 4000 and signal.shape == (4000, 2)
    assert abs(signal[:, 1]).max() == pytest.approx(abs(signal[:, 0]).max() / 2, rel=0.05)


def test_multiline_box_label():
    img = np.zeros((60, 60, 3))
    out = draw.boxes(img, [[5, 30, 40, 50]], labels=["a\nb"])  # raised "anchor not supported for multiline text"
    assert out.shape == img.shape and out.max() > 0


def test_curve_update_rescales_the_axes():
    fig, ax = plt.subplots()
    curve = Curve([SingleCurve(y=np.arange(10.0))])
    plot_object = curve.create_plot(ax=ax)
    Curve([SingleCurve(y=np.arange(10.0) * 500)]).update_plot(plot_object, ax=ax)
    assert ax.get_ylim()[1] >= 4500
    limited = Curve([SingleCurve(y=np.arange(10.0) * 500)], ylim=(0, 10))
    limited.update_plot(plot_object, ax=ax)
    assert ax.get_ylim() == (0, 10)
    plt.close(fig)


def test_unnamed_matplotlib_gui_keeps_the_user_figures():
    from interactive_pipe import interactive
    from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib
    from interactive_pipe.headless.pipeline import HeadlessPipeline

    @interactive(gain=(1.0, [0.0, 2.0]))
    def amplify_unnamed(img, gain=1.0):
        return img * gain

    def pipe(img):
        out = amplify_unnamed(img)
        return out

    user_figure = plt.figure()
    gui = InteractivePipeMatplotlib(pipeline=HeadlessPipeline.from_function(pipe, inputs=["img"]))
    assert plt.fignum_exists(user_figure.number)
    plt.close(user_figure)
    plt.close(gui.window.fig)
