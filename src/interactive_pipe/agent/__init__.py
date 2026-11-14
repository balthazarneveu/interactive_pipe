"""Instructions for coding agents, shipped with the package.

The agent skill (``build-interactive-pipeline/SKILL.md``) lives here as package
data so that ``pip install interactive-pipe`` is enough for an agent working in
another repository: ``interactive-pipe skill`` prints it and
``interactive-pipe skill --install`` copies it where Claude Code finds skills.

This file is the single source of truth; the copy in this repository's
``.claude/skills/`` is kept identical by a test (resync it with
``python -m interactive_pipe skill --install --project . --force``).

Standard library only, no import of the rest of the package.
"""

from pathlib import Path
from typing import Optional, Union

SKILL_NAME = "build-interactive-pipeline"
_HERE = Path(__file__).resolve().parent

AGENTS_MD_BLOCK = """\
## interactive_pipe

This project builds GUIs with [interactive_pipe](https://balthazarneveu.github.io/interactive_pipe/):
`@interactive(...)` filters chained by an `@interactive_pipeline` function.

- Full instructions: run `interactive-pipe skill` (or `python -m interactive_pipe skill`) and read them
  before editing a pipeline.
- The pipeline function body is parsed, not executed: only filter calls, assignments and one `return`
  (logic goes inside filters).
- You cannot see the window: check visual changes with `pipe.snapshot("/tmp/out.png", img)` or
  `interactive-pipe snapshot script.py -o /tmp/shots/`, then read the PNG; `interactive-pipe describe
  script.py` lists the controls.
- `interactive-pipe doctor` explains why no window shows up (missing backend, no display).
"""


def skill_path() -> Path:
    """Path of the installed agent skill file (``SKILL.md``)."""
    return _HERE / SKILL_NAME / "SKILL.md"


def skill_text() -> str:
    """Content of the agent skill (markdown with a YAML frontmatter)."""
    return skill_path().read_text(encoding="utf-8")


def skill_install_dir(user: bool = False, project: Optional[Union[str, Path]] = None) -> Path:
    """Folder where Claude Code looks for the skill: ``~/.claude/skills/<name>``
    (``user=True``) or ``<project>/.claude/skills/<name>``.

    Raises:
        ValueError: If both or none of ``user`` / ``project`` are given.
    """
    if user == (project is not None):
        raise ValueError("give exactly one of user=True or project=<folder>")
    base = Path.home() if user else Path(project)  # type: ignore[arg-type]
    return base / ".claude" / "skills" / SKILL_NAME


def install_skill(user: bool = False, project: Optional[Union[str, Path]] = None, force: bool = False) -> Path:
    """Copy the skill to ``~/.claude/skills/...`` or ``<project>/.claude/skills/...``.

    Returns:
        The path of the written (or already identical) ``SKILL.md``.

    Raises:
        FileExistsError: If a different ``SKILL.md`` is already there and
            ``force`` is False (it may hold local edits).
        ValueError: See ``skill_install_dir``.
    """
    target = skill_install_dir(user=user, project=project) / "SKILL.md"
    text = skill_text()
    if target.exists():
        if target.read_text(encoding="utf-8") == text:
            return target
        if not force:
            raise FileExistsError(f"{target} exists and differs from the packaged skill; pass force=True (--force)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
