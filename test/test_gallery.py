"""demo/gallery/*.py run headless, show something, and compute what their docstrings claim."""

import importlib.util
import runpy
import sys
from pathlib import Path

import numpy as np
import pytest
from test_demos_headless import _shows_something

from interactive_pipe import interactive_pipeline
from interactive_pipe.agent.run_script import run_script
from interactive_pipe.headless.control import Control

ROOT = Path(__file__).resolve().parent.parent
# g2_*.py: second dogfooding round, tested by test_gallery_g2.py, not on the gallery page yet
GALLERY = sorted(path for path in (ROOT / "demo" / "gallery").glob("*.py") if not path.stem.startswith("g2_"))


@pytest.fixture
def isolated_controls(monkeypatch):
    """Each example as if run in its own process (the control registry is keyed by module + qualname)."""
    monkeypatch.setattr(Control, "_registry", {})
    monkeypatch.setattr(Control, "_panel_cache", {})
    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)


def _load(name):
    return runpy.run_path(str(ROOT / "demo" / "gallery" / f"{name}.py"), run_name=f"gallery_{name}")


def test_gallery_has_eight_examples():
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
    assert len(source.splitlines()) <= 100, "gallery examples stay short"
    assert source.startswith('"""') and "What to look at" in source
    assert 'gui="auto"' in source and 'if __name__ == "__main__":' in source


def test_camera_isp_white_balance_maximises_psnr(isolated_controls):
    ns = _load("camera_isp")
    mosaic, demosaic, white_balance, gamma, compare = (
        ns[k] for k in ("mosaic", "demosaic", "white_balance", "gamma", "compare")
    )
    scene = ns["make_scene"]()

    def psnr(method="bilinear", red=1.8, blue=1.4):
        # filters called directly, like plain functions (compare calls layout.style)
        out = gamma(white_balance(demosaic(mosaic(scene), method=method), red=red, blue=blue))
        return float(compare(out, scene).title.split()[2])  # "error, PSNR 29.72 dB"

    assert psnr() > psnr(red=1.0, blue=1.0) + 5  # the defaults undo the sensor colour cast
    assert psnr() > psnr(method="nearest")


def test_lens_calibration_residual_vanishes_at_the_true_coefficients(isolated_controls):
    ns = _load("lens_calibration")
    k1, k2 = ns["K_TRUE"]
    assert "RMS 0.00 px" in ns["correct"](k1=k1, k2=k2).title
    assert "RMS 0.00 px" not in ns["correct"]().title


def test_blob_detection_scores(isolated_controls):
    ns = _load("blob_detection")
    blobs = ns["blob_detection"].headless  # the outputs of the GUI-decorated pipeline, no window

    img = ns["make_image"]()
    _, overlay, table = blobs(img)
    precision, recall = (float(word) for word in overlay.title.replace(",", "").split()[1::2])
    assert precision >= 0.8 and recall >= 0.6
    assert overlay.data.shape == img.shape + (3,) and len(table.values) == 11
    _, overlay, table = blobs(img, threshold=0.99)  # nothing detected: no crash
    assert overlay.title == "precision 0.00, recall 0.00" and len(table.values) == 0  # an empty Table


def test_signal_filters_have_unit_dc_gain(isolated_controls):
    ns = _load("signal_filtering")
    design, apply_filter = ns["design"], ns["apply_filter"]

    @interactive_pipeline(gui=None)
    def step_response(x):
        b, a = design()
        y = apply_filter(x, b, a)
        return y

    for kind in ("FIR", "IIR"):
        (y,) = step_response(np.ones(2000), kind=kind)
        assert abs(y[-1] - 1.0) < 1e-3


def test_pid_reaches_the_reference(isolated_controls):
    ns = _load("pid_control")
    response, command = ns["simulate"](kp=2.0, ki=3.0, kd=0.15)
    output = response.curves[1].y
    assert abs(output[-1] - 1.0) < 0.02


@pytest.mark.parametrize(
    "name, shared",
    [
        ("frequency_filtering", {"band (cycles/px)": ["band_pass.band", "radial_profile.band"]}),
        ("signal_filtering", {"cutoff (Hz)": ["design.cutoff", "bode.cutoff"]}),
        ("pid_control", {gain: [f"simulate.{gain.lower()}", f"bode.{gain.lower()}"] for gain in ("Kp", "Ki", "Kd")}),
    ],
)
def test_one_slider_drives_several_filters(name, shared, isolated_controls):
    ns = _load(name)
    controls = ns[name].describe()["controls"]
    names = [entry["name"] for entry in controls]
    assert len(names) == len(set(names))
    assert {entry["name"]: entry["targets"] for entry in controls if entry["name"] in shared} == shared


def test_reaction_diffusion_frame_depends_on_the_clock_only(isolated_controls):
    ns = _load("reaction_diffusion")
    pipe = ns["reaction_diffusion"]
    first = pipe.snapshot(None, t=1.0)
    for t in (0.5, 2.0, 1.5):  # other runs in between must not change the frame at t=1
        pipe.snapshot(None, t=t)
    np.testing.assert_array_equal(pipe.snapshot(None, t=1.0), first)
    sheet = pipe.sweep(None, t=1.0, feed=[0.03, 0.05])
    pipe.snapshot(None, t=3.0)
    np.testing.assert_array_equal(pipe.sweep(None, t=1.0, feed=[0.03, 0.05]), sheet)


def test_make_gallery_writes_small_pngs(tmp_path, isolated_controls):
    spec = importlib.util.spec_from_file_location("make_gallery", ROOT / "scripts" / "make_gallery.py")
    make_gallery = importlib.util.module_from_spec(spec)
    sys.modules["make_gallery"] = make_gallery
    spec.loader.exec_module(make_gallery)
    assert set(make_gallery.EXAMPLES) == {script.stem for script in GALLERY}
    for path in make_gallery.render("pid_control", out_dir=tmp_path):
        assert path.exists() and path.stat().st_size < 150_000


def test_gallery_page_shows_every_example():
    import re

    page = (ROOT / "docs" / "gallery.md").read_text()
    for script in GALLERY:
        assert f'--8<-- "demo/gallery/{script.name}"' in page
        assert f"images/gallery/{script.stem}.png" in page
    for image in re.findall(r"\]\((images/gallery/[\w.]+)\)", page):
        path = ROOT / "docs" / image
        assert path.is_file() and path.stat().st_size < 150_000, image
    assert "gallery.md" in (ROOT / "mkdocs.yml").read_text()
