"""The agent skill is package data, with one source of truth."""

from pathlib import Path

import pytest

import interactive_pipe
from interactive_pipe.agent import (
    AGENTS_MD_BLOCK,
    SKILL_NAME,
    install_skill,
    skill_install_dir,
    skill_path,
    skill_text,
)

ROOT = Path(__file__).resolve().parent.parent
REPO_COPY = ROOT / ".claude" / "skills" / SKILL_NAME / "SKILL.md"


def test_skill_path_is_inside_the_package():
    path = interactive_pipe.skill_path()
    assert path == skill_path()
    assert path.is_file()
    assert Path(interactive_pipe.__file__).parent in path.parents
    assert skill_text().startswith(f"---\nname: {SKILL_NAME}\n")


def test_repository_copy_is_identical_to_the_packaged_skill():
    """The packaged file is the source of truth; `.claude/skills/` is a copy for this repository.

    After editing the packaged skill (or merging a change made to the copy), resync with:
    python -m interactive_pipe skill --install --project . --force
    """
    assert REPO_COPY.read_text(encoding="utf-8") == skill_text(), (
        f"{REPO_COPY} differs from {skill_path()}: edit the packaged file and run "
        "`python -m interactive_pipe skill --install --project . --force`"
    )


def test_package_data_declares_the_skill():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"agent/*/SKILL.md"' in pyproject


def test_install_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert skill_install_dir(user=True) == tmp_path / ".claude" / "skills" / SKILL_NAME
    assert skill_install_dir(project=tmp_path / "proj") == tmp_path / "proj" / ".claude" / "skills" / SKILL_NAME
    with pytest.raises(ValueError):
        skill_install_dir()
    with pytest.raises(ValueError):
        skill_install_dir(user=True, project=tmp_path)


def test_install_refuses_to_overwrite_a_different_file(tmp_path):
    target = install_skill(project=tmp_path)
    assert target.read_text(encoding="utf-8") == skill_text()
    assert install_skill(project=tmp_path) == target  # identical: no error
    target.write_text("my local edits", encoding="utf-8")
    with pytest.raises(FileExistsError, match="--force"):
        install_skill(project=tmp_path)
    assert target.read_text(encoding="utf-8") == "my local edits"
    install_skill(project=tmp_path, force=True)
    assert target.read_text(encoding="utf-8") == skill_text()


def test_agents_md_block_points_to_the_cli():
    assert "interactive-pipe skill" in AGENTS_MD_BLOCK
    assert "snapshot" in AGENTS_MD_BLOCK
    assert AGENTS_MD_BLOCK.startswith("## interactive_pipe")
