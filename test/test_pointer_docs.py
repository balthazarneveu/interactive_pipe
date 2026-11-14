"""The python blocks of docs/guide/mouse-input.md run as written."""

from pathlib import Path

import pytest
from doc_code_blocks import extract_programs, run_program

PAGE = Path(__file__).resolve().parent.parent / "docs" / "guide" / "mouse-input.md"
PROGRAMS = extract_programs(PAGE)


def test_page_has_runnable_blocks():
    assert any(program.skip_reason is None for program in PROGRAMS)


@pytest.mark.parametrize("program", PROGRAMS, ids=[program.test_id for program in PROGRAMS])
def test_doc_block_runs(program, tmp_path, monkeypatch):
    if program.skip_reason is not None:
        pytest.skip(program.skip_reason)
    run_program(program, tmp_path, monkeypatch)
    assert (tmp_path / "seeds.png").is_file()
