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
GALLERY = sorted((ROOT / "demo" / "gallery").glob("*.py"))


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

    @interactive_pipeline(gui=None)
    def isp(gt):
        out = gamma(white_balance(demosaic(mosaic(gt))))
        error = compare(out, gt)
        return error

    scene = ns["make_scene"]()

    def psnr(method="bilinear", red=1.8, blue=1.4):
        (error,) = isp(scene, method=method, red=red, blue=blue)
        return float(error.title.split()[2])  # "error, PSNR 29.72 dB"

    assert psnr() > psnr(red=1.0, blue=1.0) + 5  # the defaults undo the sensor colour cast
    assert psnr() > psnr(method="nearest")


def test_lens_calibration_residual_vanishes_at_the_true_coefficients(isolated_controls):
    ns = _load("lens_calibration")
    k1, k2 = ns["K_TRUE"]
    assert "RMS 0.00 px" in ns["correct"](k1=k1, k2=k2).title
    assert "RMS 0.00 px" not in ns["correct"]().title


def test_blob_detection_scores(isolated_controls):
    ns = _load("blob_detection")
    detect, score = ns["detect"], ns["score"]

    @interactive_pipeline(gui=None)
    def blobs(img):
        detections = detect(img)
        overlay, table = score(img, detections)
        return overlay, table

    img = ns["make_image"]()
    overlay, table = blobs(img)
    precision, recall = (float(word) for word in overlay.title.replace(",", "").split()[1::2])
    assert precision >= 0.8 and recall >= 0.6
    assert overlay.data.shape == img.shape + (3,) and len(table.values) == 11
    overlay, table = blobs(img, threshold=0.99)  # nothing detected: no crash
    assert overlay.title == "precision 0.00, recall 0.00" and table == "no detection"


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
    pid = (2.0, 3.0, 0.15)
    response, command = ns["simulate"](pid)
    output = response.curves[1].y
    assert abs(output[-1] - 1.0) < 0.02


def test_reaction_diffusion_frame_depends_on_the_clock_only(isolated_controls):
    ns = _load("reaction_diffusion")
    pipe = ns["reaction_diffusion"]
    first = pipe.snapshot(None, t=1.0)
    for t in (0.5, 2.0, 1.5):  # other runs in between must not change the frame at t=1
        pipe.snapshot(None, t=t)
    np.testing.assert_array_equal(pipe.snapshot(None, t=1.0), first)


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
