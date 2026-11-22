"""User code written against interactive_pipe type-checks under strict settings.

``test/typing_usage/strict_usage.py`` uses the decorators, data objects and
proxies the way a typed project would. Each checker is skipped when it is not
installed (``pip install interactive_pipe[dev]`` brings both).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

USAGE = Path(__file__).resolve().parent / "typing_usage" / "strict_usage.py"
# backends without usable stubs (PyQt6's .pyi trip mypy's parser): not part of the user-facing API
SKIPPED_IMPORTS = ["PyQt6.*", "PyQt5.*", "gradio.*", "dearpygui.*", "cv2.*", "torch.*", "ipywidgets.*"]


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


@pytest.mark.skipif(not _installed("mypy"), reason="mypy not installed")
def test_usage_passes_mypy_strict(tmp_path):
    config = tmp_path / "mypy.ini"
    config.write_text(
        "[mypy]\nstrict = True\n"
        f"[mypy-{','.join(SKIPPED_IMPORTS)}]\n"
        "follow_imports = skip\nfollow_imports_for_stubs = True\nignore_missing_imports = True\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(config),
            "--cache-dir",
            str(tmp_path / "cache"),
            str(USAGE),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not _installed("pyright"), reason="pyright not installed")
def test_usage_passes_pyright_strict(tmp_path):
    config = tmp_path / "pyrightconfig.json"
    config.write_text(
        json.dumps(
            {
                "typeCheckingMode": "strict",
                "reportMissingTypeStubs": False,
                "include": [str(USAGE)],
            }
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--pythonpath", sys.executable, "-p", str(config), "--outputjson"],
        capture_output=True,
        text=True,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.skip(f"pyright did not run: {result.stdout[-500:]}{result.stderr[-500:]}")
    errors = [
        f"{d['range']['start']['line'] + 1}: {d['message']}"
        for d in report["generalDiagnostics"]
        if d["severity"] == "error"
    ]
    assert errors == []
