"""Every show reel reference keeps passing its grader (runs headless, live controls, line budget)."""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SHOWREEL = Path(__file__).resolve().parent.parent / "showreel"
PROMPTS = sorted((SHOWREEL / "prompts").glob("[0-9][0-9]_*.md"))
NEEDS_TORCH = {"mlp_decision_boundary", "signal_propagation"}


def _budget(prompt: Path) -> int:
    match = re.search(r"Line budget: (\d+)", prompt.read_text())
    if match is None:
        raise ValueError(f"no line budget in {prompt.name}")
    return int(match.group(1))


@pytest.mark.parametrize("prompt", PROMPTS, ids=[prompt.stem[3:] for prompt in PROMPTS])
def test_reference_demo_passes_the_grader(prompt, tmp_path):
    name = prompt.stem[3:]
    if name in NEEDS_TORCH and importlib.util.find_spec("torch") is None:
        pytest.skip("PyTorch is not installed")
    demo = SHOWREEL / "demos" / f"{name}.py"
    assert demo.exists(), f"no reference demo for the prompt {prompt.name}"
    subprocess.run(
        [sys.executable, str(SHOWREEL / "tools" / "grade.py"), str(demo), "--out", str(tmp_path)]
        + ["--max-lines", str(_budget(prompt))],
        capture_output=True,
        check=False,
    )
    report = json.loads((tmp_path / "report.json").read_text())
    problems = report["static"]["problems"] + report["dynamic"]["problems"]
    assert not problems, "\n".join(problems)
