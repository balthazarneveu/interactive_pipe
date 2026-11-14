"""Every script of demo/ and samples/ runs headless and shows something.

Each script is run unmodified, as ``__main__``, the way
``interactive-pipe snapshot`` runs it (``INTERACTIVE_PIPE_SNAPSHOT`` + snapshot
hook): every GUI-decorated pipeline call writes a PNG instead of opening a
window. The PNG must exist and not be blank. Scripts that cannot produce one are
listed below with the reason, so nothing is skipped silently.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

from interactive_pipe.agent.run_script import run_script
from interactive_pipe.headless.control import Control

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "demo").glob("*.py")) + sorted((ROOT / "samples").glob("*.py"))

#: script name -> reason: runs fine (exit code 0) but has no GUI pipeline to snapshot
NO_GUI_PIPELINE = {
    "object_oriented_pipeline_declarations.py": "HeadlessPipeline built from FilterCore objects, no GUI",
}

#: script name -> reason: not run at all
NOT_RUN = {}

#: Not collected (outside demo/*.py and samples/*.py): samples/interact_sample/ uses @interact,
#: which opens its window at import time and ignores INTERACTIVE_PIPE_SNAPSHOT;
#: demo/multi_image.ipynb is a notebook.


def _is_blank(path: Path) -> bool:
    from matplotlib.image import imread

    pixels = imread(str(path))[..., :3].astype(np.float64)
    return float(pixels.std()) < 0.01


def test_every_listed_script_exists():
    names = {script.name for script in SCRIPTS}
    assert set(NO_GUI_PIPELINE) <= names and set(NOT_RUN) <= names
    assert len(SCRIPTS) >= 19


@pytest.mark.parametrize("script", SCRIPTS, ids=[f"{script.parent.name}/{script.name}" for script in SCRIPTS])
def test_script_renders_headless(script, tmp_path, monkeypatch):
    if script.name in NOT_RUN:
        pytest.skip(NOT_RUN[script.name])
    monkeypatch.chdir(tmp_path)  # scripts writing files (graphs, exports) write here
    # every script runs as __main__: isolate the control registry (keyed by module + qualname),
    # as if each script ran in its own process like `interactive-pipe snapshot` does
    monkeypatch.setattr(Control, "_registry", {})
    monkeypatch.setattr(Control, "_panel_cache", {})
    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)
    # graph_representation(view=True) (samples/) would open an image viewer when graphviz is installed
    monkeypatch.setitem(sys.modules, "graphviz", None)
    run = run_script(str(script), output=f"{tmp_path.as_posix()}/shots/", max_calls=3)
    assert run.exit_code == 0, run.error
    if script.name in NO_GUI_PIPELINE:
        assert run.written == []
        return
    assert run.written, f"{script.name} called no GUI pipeline"
    for path in run.written:
        assert path.stat().st_size > 2000, path
        assert not _is_blank(path), f"{path} is blank"


# --- demo fixes ---------------------------------------------------------------------------------

BLUR_DEMOS = ["grouped_controls_demo.py", "detached_panel_demo.py", "panel_demo.py", "panel_position_demo.py"]


def _demo_namespace(name):
    import runpy

    return runpy.run_path(str(ROOT / "demo" / name), run_name="demo_under_test")  # skips the __main__ block


def _reference_blur(result, radius):
    """The per-pixel loop the demos used (several seconds per slider move on a 512x512 image)."""
    h, w = result.shape[:2]
    blurred = result.copy()
    for y in range(h):
        for x in range(w):
            blurred[y, x] = result[y, max(0, x - radius) : min(w, x + radius + 1)].mean(axis=0)
    return blurred


@pytest.mark.parametrize("name", BLUR_DEMOS)
def test_demo_blur_matches_the_former_loop(name):
    blur = _demo_namespace(name)["horizontal_box_blur"]
    img = np.random.default_rng(0).random((7, 11, 3))
    for radius in (1, 3, 20):
        np.testing.assert_allclose(blur(img, radius), _reference_blur(img, radius), atol=1e-12)
    assert blur(img[..., 0], 2).shape == (7, 11)


def test_panel_position_default_crop_keeps_the_whole_image():
    process_image = _demo_namespace("panel_position_demo.py")["process_image"]
    img = np.random.default_rng(0).random((512, 384, 3))
    from interactive_pipe.core.context import _set_framework_state
    from interactive_pipe.core.framework_state import FrameworkState

    _set_framework_state(FrameworkState())  # process_image calls layout.style
    try:
        assert process_image(img).shape == img.shape
        assert process_image(img, crop_x=50, crop_width=50).shape == (512, 192, 3)
    finally:
        _set_framework_state(None)
