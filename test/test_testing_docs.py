"""The python blocks of docs/guide/testing.md run as written."""

from pathlib import Path

import pytest
from doc_code_blocks import extract_programs, run_program

PAGE = Path(__file__).resolve().parent.parent / "docs" / "guide" / "testing.md"
PROGRAMS = extract_programs(PAGE)


def test_page_has_runnable_blocks():
    assert sum(program.skip_reason is None for program in PROGRAMS) == 3


@pytest.mark.parametrize("program", PROGRAMS, ids=[program.test_id for program in PROGRAMS])
def test_doc_block_runs(program, tmp_path, monkeypatch):
    run_program(program, tmp_path, monkeypatch)
