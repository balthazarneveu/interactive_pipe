"""The python blocks of the pages newcomers and agents land on run as written.

The skill has its own test (test_skill_code_blocks.py). Markers above a block
(skip with a reason, continue, raises, file) are described in doc_code_blocks.py.
"""

from pathlib import Path

import pytest
from doc_code_blocks import extract_programs, run_program

ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    ROOT / "readme.md",
    ROOT / "docs" / "getting-started" / "quickstart.md",
]
# docs/guide/snapshots.md is not listed: its example reads demo/images/ and regenerates the
# docs/images/ pictures shown on the page (run it from the repository root to update them).
PROGRAMS = [program for page in PAGES for program in extract_programs(page)]


@pytest.mark.parametrize("page", PAGES, ids=[page.name for page in PAGES])
def test_page_has_runnable_blocks(page):
    assert any(program.skip_reason is None for program in extract_programs(page))


@pytest.mark.parametrize("program", PROGRAMS, ids=[program.test_id for program in PROGRAMS])
def test_doc_block_runs(program, tmp_path, monkeypatch):
    if program.skip_reason is not None:
        pytest.skip(program.skip_reason)
    run_program(program, tmp_path, monkeypatch)


def test_quickstart_library_example_uses_the_library_file(tmp_path, monkeypatch):
    quickstart = extract_programs(PAGES[1])
    app = next(program for program in quickstart if "image_filters.py" in program.files)
    run_program(app, tmp_path, monkeypatch)
    assert (tmp_path / "image_filters.py").is_file()
    assert (tmp_path / "results" / "sample_blended.png").is_file()  # the `save` continuation ran


def test_readme_quick_taste_writes_a_snapshot(tmp_path, monkeypatch):
    run_program(extract_programs(PAGES[0])[0], tmp_path, monkeypatch)
    assert (tmp_path / "shots" / "pipe.png").stat().st_size > 1000


def test_markers(tmp_path):
    page = tmp_path / "page.md"
    page.write_text(
        "<!-- code: file lib.py -->\n```python\nX = 1\n```\n\n"
        "```python\nfrom lib import X\n```\n\n"
        "<!-- code: raises ZeroDivisionError -->\n```python\n1 / 0\n```\n\n"
        "<!-- code: continue -->\n```python\nY = X + 1\n```\n\n"
        "<!-- code: skip needs a camera -->\n```python\ncamera()\n```\n\n"
        "```bash\nnot python\n```\n",
        encoding="utf-8",
    )
    programs = extract_programs(page)
    assert [program.lineno for program in programs] == [6, 11, 21]
    first, raising, skipped = programs
    assert first.files == {"lib.py": "X = 1\n"}
    assert first.source == "from lib import X\n\nY = X + 1\n"  # continue skips the raises block
    assert raising.raises == "ZeroDivisionError" and skipped.skip_reason == "needs a camera"


@pytest.mark.parametrize(
    "markdown",
    [
        "<!-- code: skip -->\n```python\nx\n```\n",  # no reason
        "<!-- code: continue -->\n```python\nx\n```\n",  # nothing to continue
        "<!-- code: file notes.txt -->\n```python\nx\n```\n",
    ],
)
def test_invalid_markers(tmp_path, markdown):
    page = tmp_path / "page.md"
    page.write_text(markdown, encoding="utf-8")
    with pytest.raises(ValueError):
        extract_programs(page)


def test_run_program_checks_raises(tmp_path, monkeypatch):
    page = tmp_path / "page.md"
    page.write_text("<!-- code: raises KeyError -->\n```python\nx = 1\n```\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="should raise KeyError"):
        run_program(extract_programs(page)[0], tmp_path / "work", monkeypatch)
