"""Every python block of the agent skill runs (headless) as written."""

from pathlib import Path

import pytest
from doc_code_blocks import extract_programs, run_program

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "build-interactive-pipeline" / "SKILL.md"
PROGRAMS = extract_programs(SKILL)


def test_skill_has_runnable_blocks():
    assert len([program for program in PROGRAMS if program.skip_reason is None]) >= 2


@pytest.mark.parametrize("program", PROGRAMS, ids=[program.test_id for program in PROGRAMS])
def test_skill_block_runs(program, tmp_path, monkeypatch):
    if program.skip_reason is not None:
        pytest.skip(program.skip_reason)
    run_program(program, tmp_path, monkeypatch)


def test_skill_scaffold_snapshot_is_written(tmp_path, monkeypatch):
    run_program(PROGRAMS[0], tmp_path, monkeypatch)
    assert (tmp_path / "shots" / "my_pipeline.png").stat().st_size > 1000


def test_skill_frontmatter():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\nname: build-interactive-pipeline\ndescription: ")
    description = text.split("\n")[2]
    for keyword in ("GUI", "slider", "snapshot", "headless", "image"):
        assert keyword in description
    assert len(text.splitlines()) < 200
