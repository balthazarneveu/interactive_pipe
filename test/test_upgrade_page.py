"""docs/upgrade-from-0.9.md: every "after" block runs, every "before" block marked `raises` raises."""

import re
from pathlib import Path

import pytest
from doc_code_blocks import extract_programs, run_program

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "upgrade-from-0.9.md"
PROGRAMS = extract_programs(PAGE)


@pytest.mark.parametrize("program", PROGRAMS, ids=[program.test_id for program in PROGRAMS])
def test_upgrade_block(program, tmp_path, monkeypatch):
    assert program.skip_reason is None  # nothing on this page is left untested
    run_program(program, tmp_path, monkeypatch)


def _anchors(page):
    """Heading anchors as mkdocs (python-markdown toc) makes them."""
    anchors = set()
    for line in page.splitlines():
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            text = re.sub(r"[^\w\s-]", "", text).strip().lower()
            anchors.add(re.sub(r"[-\s]+", "-", text))
    return anchors


def _behaviour_changes():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = changelog.index("## 0.9.5")  # the release this page documents
    release = changelog[start : changelog.index("\n## ", start + 5)]
    section = release[release.index("### Changes that can affect existing code") :]
    section = section[: section.index("\n### ", 5)]
    return [line for line in section.splitlines() if line.startswith("- ")]


def test_every_behaviour_change_of_the_changelog_links_to_the_page():
    anchors = _anchors(PAGE.read_text(encoding="utf-8"))
    changes = _behaviour_changes()
    assert len(changes) >= 20
    for line in changes:
        links = re.findall(r"upgrade-from-0\.9/#([\w-]+)", line)
        assert links, f"no link to the upgrade page: {line[:80]}"
        for anchor in links:
            assert anchor in anchors, f"unknown anchor #{anchor} in: {line[:80]}"


def test_page_is_in_the_nav():
    assert "upgrade-from-0.9.md" in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
