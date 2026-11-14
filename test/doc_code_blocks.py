"""Extract the python code blocks of a markdown file and run them headless.

Used by the tests checking that the code shown to users and coding agents
(skill, readme, quickstart) actually runs. Every ```python block is run,
unless the HTML comment on the line right above it says otherwise:

- ``<!-- code: skip <reason> -->``: not runnable on its own (fragment, needs a
  file or hardware...); the reason is mandatory, so nothing is skipped silently.
- ``<!-- code: continue -->``: appended to the previous plain runnable block (which
  is then run once, with all its continuations).
- ``<!-- code: raises <ExceptionName> -->``: must raise that exception.
- ``<!-- code: file <name.py> -->``: not run, written as ``name.py`` next to
  every later block of the same file (a module imported by the next examples).

Blocks run in a temporary folder with ``INTERACTIVE_PIPE_SNAPSHOT`` set, so a
GUI launch writes a PNG instead of opening a window; ``/tmp/`` in the source is
redirected to that folder.
"""

import re
import runpy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_FENCE_OPEN = re.compile(r"^(\s*)```(\w*)\s*$")
_MARKER = re.compile(r"^\s*<!--\s*code:\s*(skip|continue|raises|file)\b\s*(.*?)\s*-->\s*$")


@dataclass
class CodeProgram:
    """One runnable unit: a block and its continuations."""

    path: Path
    lineno: int  # line of the first block's opening fence
    source: str
    raises: Optional[str] = None
    skip_reason: Optional[str] = None
    blocks: List[int] = field(default_factory=list)
    files: Dict[str, str] = field(default_factory=dict)  # `code: file` blocks seen before it

    @property
    def test_id(self) -> str:
        return f"{self.path.name}:{self.lineno}"


def extract_programs(path: Path) -> List[CodeProgram]:
    """Python programs of a markdown file, with their markers applied."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    programs: List[CodeProgram] = []
    files: Dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = _FENCE_OPEN.match(lines[index])
        if not match or match.group(2) not in ("python", "py"):
            index += 1
            continue
        indent = match.group(1)
        marker = _MARKER.match(lines[index - 1]) if index > 0 else None
        start = index
        body: List[str] = []
        index += 1
        while index < len(lines) and lines[index].strip() != "```":
            line = lines[index]
            body.append(line[len(indent) :] if line.startswith(indent) else line)
            index += 1
        index += 1
        source = "\n".join(body) + "\n"
        kind = marker.group(1) if marker else None
        argument = marker.group(2) if marker else ""
        if kind == "file":
            if not argument.endswith(".py"):
                raise ValueError(f"{path}:{start + 1}: `code: file` needs a python file name")
            files[argument] = source
        elif kind == "skip":
            if not argument:
                raise ValueError(f"{path}:{start + 1}: `code: skip` needs a reason")
            programs.append(CodeProgram(path, start + 1, source, skip_reason=argument, blocks=[start + 1]))
        elif kind == "continue":
            runnable = [program for program in programs if program.skip_reason is None and program.raises is None]
            if not runnable:
                raise ValueError(
                    f"{path}:{start + 1}: `code: continue` needs a previous plain block (not skip / raises)"
                )
            runnable[-1].source += "\n" + source
            runnable[-1].blocks.append(start + 1)
        else:
            raises = argument if kind == "raises" else None
            if kind == "raises" and not raises:
                raise ValueError(f"{path}:{start + 1}: `code: raises` needs an exception name")
            programs.append(CodeProgram(path, start + 1, source, raises=raises, blocks=[start + 1], files=dict(files)))
    return programs


def run_program(program: CodeProgram, workdir: Path, monkeypatch) -> None:
    """Run a program as a script in `workdir`, headless; check `raises`."""
    workdir.mkdir(parents=True, exist_ok=True)
    source = program.source.replace("/tmp/", f"{workdir.as_posix()}/")
    script = workdir / f"block_{program.lineno}.py"
    script.write_text(source, encoding="utf-8")
    for name, content in program.files.items():
        (workdir / name).write_text(content, encoding="utf-8")
    monkeypatch.syspath_prepend(str(workdir))
    for name in program.files:  # import the fresh file, not a module cached by another block
        monkeypatch.delitem(sys.modules, Path(name).stem, raising=False)
    monkeypatch.chdir(workdir)
    # every block runs as __main__: a fresh control registry (keyed by module + qualname) per block,
    # as if each ran in its own interpreter
    from interactive_pipe.headless.control import Control

    monkeypatch.setattr(Control, "_registry", {})
    monkeypatch.setattr(Control, "_panel_cache", {})
    monkeypatch.setenv("INTERACTIVE_PIPE_SNAPSHOT", f"{(workdir / 'shots').as_posix()}/")
    monkeypatch.setenv("MPLBACKEND", "Agg")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("INTERACTIVE_PIPE_GUI", raising=False)
    location = f"{program.path}:{program.blocks}"
    try:
        runpy.run_path(str(script), run_name="__main__")
    except Exception as exc:  # noqa: BLE001 - reported with the block location
        if program.raises is not None and type(exc).__name__ == program.raises:
            return
        raise AssertionError(f"code block {location} raised {type(exc).__name__}: {exc}") from exc
    finally:
        for name in program.files:
            sys.modules.pop(Path(name).stem, None)
    if program.raises is not None:
        raise AssertionError(f"code block {location} should raise {program.raises}")
