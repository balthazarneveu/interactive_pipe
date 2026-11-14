"""``import interactive_pipe`` stays light: matplotlib.pyplot, the GUI toolkits
and the heavy optional dependencies (cv2, pandas) are imported when used, not
at import time (``interactive-pipe --help`` used to take ~1 s because of them)."""

import importlib.util
import json
import os
import subprocess
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

NOT_AT_IMPORT = [
    "matplotlib.pyplot",
    "PyQt6",
    "PyQt5",
    "PySide6",
    "dearpygui",
    "gradio",
    "ipywidgets",
    "cv2",
    "pandas",
]


def _modules_after(code: str) -> set:
    env = {**os.environ, "PYTHONPATH": SRC + os.pathsep + os.environ.get("PYTHONPATH", "")}
    env.pop("MPLBACKEND", None)
    script = code + "\nimport json, sys\nprint(json.dumps(sorted(sys.modules)))"
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120)
    assert done.returncode == 0, done.stderr
    return set(json.loads(done.stdout.strip().splitlines()[-1]))


def test_import_does_not_load_pyplot_nor_gui_toolkits():
    modules = _modules_after("import interactive_pipe")
    loaded = [name for name in NOT_AT_IMPORT if name in modules]
    assert loaded == [], f"imported by `import interactive_pipe`: {loaded}"


def test_command_line_help_does_not_load_them_either():
    modules = _modules_after(
        "import sys\nfrom interactive_pipe.agent.command_line import build_parser\nbuild_parser().format_help()"
    )
    loaded = [name for name in NOT_AT_IMPORT if name in modules]
    assert loaded == [], f"imported by the command line: {loaded}"


def test_lazy_dependencies_still_work(tmp_path):
    # the availability lists are computed without importing; the features import on use
    import numpy as np

    from interactive_pipe import Curve, Image, Table
    from interactive_pipe.data_objects.curves import SIGNAL_BACKEND_MPL, signal_backends
    from interactive_pipe.data_objects.image import image_backends

    assert SIGNAL_BACKEND_MPL in signal_backends and image_backends
    Image(np.zeros((4, 4, 3))).save(tmp_path / "img.png")
    assert Image.load_image(tmp_path / "img.png").shape == (4, 4, 3)
    Curve([np.linspace(0, 1, 5)]).save(tmp_path / "curve.png")
    assert (tmp_path / "curve.png").stat().st_size > 0
    table = Table({"a": [1, 2]})
    if importlib.util.find_spec("pandas") is not None:  # optional extra, absent from the CI test install
        assert list(table.as_dataframe()["a"]) == [1, 2]
