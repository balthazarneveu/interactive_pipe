"""demo/gallery/g2_*.py (second dogfooding round): each renders headless, shows something and
does what its docstring says. Filters are tested as plain functions and through `.headless`."""

import runpy
from pathlib import Path

import numpy as np
import pytest
from test_demos_headless import _shows_something

from interactive_pipe.agent.run_script import run_script
from interactive_pipe.headless.control import Control

ROOT = Path(__file__).resolve().parent.parent
GALLERY = sorted((ROOT / "demo" / "gallery").glob("g2_*.py"))


@pytest.fixture
def isolated_controls(monkeypatch):
    """Each example as if run in its own process (the control registry is keyed by module + qualname)."""
    monkeypatch.setattr(Control, "_registry", {})
    monkeypatch.setattr(Control, "_panel_cache", {})
    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)


def _load(name):
    return runpy.run_path(str(ROOT / "demo" / "gallery" / f"g2_{name}.py"), run_name=f"gallery_g2_{name}")


def test_eight_examples():
    assert len(GALLERY) == 8


@pytest.mark.parametrize("script", GALLERY, ids=[script.stem for script in GALLERY])
def test_example_renders_headless(script, tmp_path, monkeypatch, isolated_controls):
    monkeypatch.chdir(tmp_path)
    run = run_script(str(script), output=f"{tmp_path.as_posix()}/shots/", max_calls=1)
    assert run.exit_code == 0, run.error
    assert len(run.calls) == 1, f"{script.name} should call its GUI pipeline once"
    call = run.calls[0]
    assert call.path.stat().st_size > 2000
    assert _shows_something(call.results), f"{call.path}: every output is blank"


@pytest.mark.parametrize("script", GALLERY, ids=[script.stem for script in GALLERY])
def test_example_is_short_and_documented(script):
    source = script.read_text()
    assert len(source.splitlines()) <= 100
    assert source.startswith('"""') and "What to look at" in source
    assert 'gui="auto"' in source and 'if __name__ == "__main__":' in source


def test_stereo_window_trades_noise_for_edges(isolated_controls):
    ns = _load("stereo_matching")
    block_match, disparity_error = ns["block_match"], ns["disparity_error"]
    left, right, truth = ns["make_views"]()

    def bad_pixels(**params):
        disparity, _ = block_match(left, right, **params)  # a plain call
        return np.mean(np.abs(disparity_error(disparity, truth)) > 1)

    assert bad_pixels(window=5) < bad_pixels(window=1) / 5  # noise averaged out
    disparity, _ = block_match(left, right, max_disparity=10)
    assert disparity.max() <= 10 and np.mean(disparity[30:80, 95:145] == 14) == 0  # the square is clipped

    # through the GUI-decorated pipeline, no window: the cost curve's minimum is the true disparity
    marked, right_view, cost, *_ = (
        cell for row in ns["g2_stereo_matching"].headless(left, right, truth) for cell in row
    )
    assert cost.title == "matching cost, minimum at 9 px"  # the default probe is on the disc (9 px)
    assert marked.shape == left.shape + (3,)


def test_segmentation_iou_peaks_at_moderate_smoothing(isolated_controls):
    ns = _load("segmentation")
    pipe = ns["g2_segmentation"]
    img, truth = ns["make_image"]()

    def iou(**params):
        (smoothed, overlay), (hist, confusion) = pipe.headless(img, truth, **params)
        counts = np.array([row[1:] for row in confusion.values])  # truth x predicted
        return np.mean([counts[k, k] / (counts[k].sum() + counts[:, k].sum() - counts[k, k]) for k in range(3)])

    assert iou(radius=2) > iou(radius=0) + 0.1
    assert iou(radius=2) > iou(radius=5) + 0.1
    assert iou(radius=2, method="k-means") > 0.75  # k-means finds thresholds as good as the hand-set ones
    labels = ns["segment"](img, thresholds=(0.35, 0.65))  # a plain call
    assert set(np.unique(labels)) == {0, 1, 2}


def test_kalman_compromise_and_shared_sliders(isolated_controls):
    ns = _load("kalman_tracking")
    truth, measurements = ns["make_track"]()

    def rms(filter_name, q):
        estimates, _ = ns[filter_name](measurements, q=q, r=1.0)
        return np.sqrt(np.mean((estimates - truth) ** 2))

    assert rms("constant_acceleration", 1.0) < rms("constant_velocity", 1.0)  # at the default q
    assert rms("constant_velocity", 100.0) < min(rms("constant_velocity", 1.0), rms("constant_velocity", 1e5))
    controls = {entry["name"]: entry["targets"] for entry in ns["g2_kalman_tracking"].describe()["controls"]}
    assert controls == {
        "process noise q": ["constant_velocity.q", "constant_acceleration.q"],
        "measurement noise r": ["constant_velocity.r", "constant_acceleration.r"],
    }


def test_beamforming_side_lobes_and_grating_lobes(isolated_controls):
    ns = _load("beamforming")
    array_factor_db, angles = ns["array_factor_db"], ns["ANGLES"]
    # 16 elements at broadside, half a wavelength: main lobe to the first null, 7.2 deg (Hann: 14.5 deg)
    assert array_factor_db(16, 0.5, 0.0, "uniform")[np.abs(angles) > 7.2].max() == pytest.approx(-13.2, abs=0.3)
    assert array_factor_db(16, 0.5, 0.0, "hann")[np.abs(angles) > 14.5].max() < -30
    spacing_map = ns["spacing_map"](elements=8, steering=0.0)  # plain call; rows = spacing, columns = -90..90 deg
    assert spacing_map[-1, 90 + 30] > -0.1  # 2 wavelengths: a full grating lobe at 30 deg
    half = np.argmin(np.abs(ns["SPACINGS"] - 0.5))
    assert spacing_map[half, np.abs(np.arange(-90, 91)) > 15].max() < -10  # no grating lobe at half a wavelength


def test_dct_quality_and_high_frequencies(isolated_controls):
    ns = _load("dct_compression")
    img = ns["make_image"]()
    curve, table = ns["rate_distortion"](img)
    quality, rate, psnr = (np.array(column, dtype=float) for column in zip(*table.values))
    assert np.all(np.diff(rate) > 0) and np.all(np.diff(psnr) > 0)
    stripes = slice(80, 128)
    kept, _ = ns["compress"](img, quality=90)
    dropped, _ = ns["compress"](img, quality=90, zero_high=True)
    assert kept[stripes].std() > 0.15 and dropped[stripes].std() < 0.05  # the stripes vanish


def test_heat_diffusion_is_reproducible_and_conserves_heat(isolated_controls):
    ns = _load("heat_diffusion")
    pipe, plate = ns["g2_heat_diffusion"], ns["initial_plate"]()
    first = pipe.snapshot(None, plate, step=500)
    pipe.snapshot(None, step=200)
    pipe.snapshot(None, step=900, edges="insulated")
    np.testing.assert_array_equal(pipe.snapshot(None, step=500), first)

    # GUI-like: successive runs share the context cache; continuing must equal a fresh solve
    pipe.headless(plate, step=300)
    at_500, _ = pipe.headless(plate, step=500)
    fresh = plate.copy()
    for _ in range(500):
        fresh = ns["step_once"](fresh, 0.2, "cold")
    np.testing.assert_allclose(at_500, fresh)

    simulate = ns["simulate"]
    assert simulate(plate, step=1000, edges="insulated").mean() == pytest.approx(plate.mean())
    assert simulate(plate, step=1000, edges="cold").mean() < 0.7 * plate.mean()
    assert np.abs(simulate(plate, step=600, r=0.26)).max() > 1e6  # unstable above 0.25


def test_training_curves_ranking_and_empty_selection(isolated_controls):
    ns = _load("training_curves")
    runs, inspect_runs = ns["make_runs"](), ns["inspect_runs"]

    def best(**params):
        _, table = inspect_runs(runs, **params)
        return next(row[0] for row in table.values if row[-1] == "*")

    assert best(smoothing=0.9) == "lr 0.03"
    assert best(smoothing=0.0) == "lr 0.01"  # by luck, as the docstring says
    ax, table = inspect_runs(runs, threshold=0.99)
    assert table.values == [] and not ax.lines


def test_audio_drive_adds_harmonics_and_delay_echoes(isolated_controls):
    ns = _load("audio_effects")
    chord, rate = ns["make_chord"](), ns["RATE"]

    def high_band_energy(signal):
        spectrum = np.abs(np.fft.rfft(signal)) ** 2
        freqs = np.fft.rfftfreq(len(signal), 1 / rate)
        return spectrum[freqs > 1000].sum() / spectrum.sum()

    assert high_band_energy(ns["distortion"](chord, drive=15.0)) > 10 * high_band_energy(
        ns["distortion"](chord, drive=1.0)
    )
    echo = ns["delay"](chord, delay_ms=250.0, feedback=0.0, mix=1.0)  # wet only: the chord, 250 ms later
    d = rate // 4
    assert np.abs(chord).max() < 1  # so the output is not rescaled
    np.testing.assert_allclose(echo[d : d + len(chord)], chord)
    assert np.all(echo[:d] == 0)
