"""Run an unmodified user script without opening any window.

Used by ``interactive-pipe snapshot`` and ``interactive-pipe describe``. The
script runs in this process as ``__main__`` (so pipelines called under
``if __name__ == "__main__":`` are reached), with ``INTERACTIVE_PIPE_SNAPSHOT``
set and a snapshot hook (``interactive_pipe.cli.set_snapshot_hook``) that sees
every call of a GUI-decorated pipeline.

Several pipelines, several calls: every call writes its own PNG, named after
the pipeline (``<folder>/<pipeline>.png``, then ``<pipeline>_2.png`` ... when the
same pipeline is called again; with a file name ``out.png``: ``out.png``,
``out_2.png`` ...). After ``max_calls`` calls the script is stopped, so a script
looping over a dataset does not run forever.
"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

DEFAULT_MAX_CALLS = 10


class _StopScript(BaseException):
    """Raised from the hook to stop the user script once enough calls were seen.

    A BaseException so that ``except Exception`` blocks of the script do not
    swallow it."""


@dataclass
class PipelineCall:
    """One call of a GUI-decorated pipeline seen while running the script."""

    name: str
    path: Optional[Path]
    description: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None


@dataclass
class ScriptRun:
    """What happened while running the script."""

    script: Path
    calls: List[PipelineCall] = field(default_factory=list)
    exit_code: int = 0
    error: Optional[str] = None
    stopped_early: bool = False

    @property
    def written(self) -> List[Path]:
        return [call.path for call in self.calls if call.path is not None]


def default_output(script: Path) -> Path:
    """Folder used when no output is given: outside the user's repository."""
    return Path(tempfile.gettempdir()) / "interactive_pipe_snapshots" / script.stem


def _is_folder(output: str) -> bool:
    # same rule as INTERACTIVE_PIPE_SNAPSHOT: a trailing slash or an existing folder
    return output.endswith(("/", os.sep)) or Path(output).is_dir()


class _PathChooser:
    """File name of each snapshot, unique within one run."""

    def __init__(self, output: str):
        self.output = output
        self.used: set = set()

    def __call__(self, name: str) -> Path:
        if "{name}" in self.output:
            base = Path(self.output.replace("{name}", name))
        elif _is_folder(self.output):
            base = Path(self.output) / f"{name}.png"
        else:
            base = Path(self.output)
        if not base.suffix:
            base = base.with_suffix(".png")
        candidate, index = base, 2
        while candidate in self.used:
            candidate = base.with_name(f"{base.stem}_{index}{base.suffix}")
            index += 1
        self.used.add(candidate)
        return candidate


def run_script(
    script: str,
    script_args: Sequence[str] = (),
    output: Optional[str] = None,
    describe: bool = False,
    max_calls: int = DEFAULT_MAX_CALLS,
) -> ScriptRun:
    """Run `script` headless; every GUI-decorated pipeline call writes a PNG.

    Args:
        script: Path of the python script.
        script_args: Its command line arguments (``sys.argv[1:]``).
        output: PNG file, folder, or pattern with ``{name}``; defaults to
            ``default_output(script)``. Ignored when ``describe`` is True.
        describe: Record ``describe()`` / ``summary()`` of each pipeline
            instead of keeping the PNGs (rendered in a temporary folder).
        max_calls: Stop the script after this many pipeline calls.

    Raises:
        FileNotFoundError: If the script does not exist.
        ValueError: If ``max_calls`` is not positive.
    """
    from interactive_pipe.cli import SNAPSHOT_ENV_VAR, set_snapshot_hook

    script_path = Path(script).resolve()
    if not script_path.is_file():
        raise FileNotFoundError(f"script not found: {script}")
    if max_calls < 1:
        raise ValueError(f"max_calls should be at least 1, got {max_calls}")
    scratch = tempfile.TemporaryDirectory(prefix="interactive_pipe_describe_") if describe else None
    if scratch is not None:
        output = f"{Path(scratch.name).as_posix()}/"
    elif output is None:
        output = f"{default_output(script_path).as_posix()}/"
    run = ScriptRun(script=script_path)
    choose_path = _PathChooser(output)

    def hook(name: str, pipeline: Any, render: Callable[[Path], Any]) -> Any:
        path = choose_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if describe:  # the PNG goes to a temporary folder, deleted afterwards
            with contextlib.redirect_stdout(io.StringIO()):
                results = render(path)
        else:
            results = render(path)
        call = PipelineCall(name=name, path=None if describe else path)
        if describe:
            call.description = pipeline.describe()
            call.summary = pipeline.summary()
        run.calls.append(call)
        if len(run.calls) >= max_calls:
            raise _StopScript()
        return results

    saved_argv, saved_path = sys.argv, list(sys.path)
    saved_env = {name: os.environ.get(name) for name in (SNAPSHOT_ENV_VAR, "INTERACTIVE_PIPE_GUI", "QT_QPA_PLATFORM")}
    os.environ[SNAPSHOT_ENV_VAR] = output  # also used by filter.interact()
    os.environ.pop("INTERACTIVE_PIPE_GUI", None)  # "headless" there would bypass the snapshots
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    previous_hook = set_snapshot_hook(hook)
    import matplotlib

    saved_mpl_backend = matplotlib.get_backend()
    matplotlib.use("Agg", force=True)  # a plt.show() in the script must not open a window
    sys.argv = [str(script_path), *script_args]
    sys.path.insert(0, str(script_path.parent))
    # describe: the script's own prints go to stderr, stdout is the description (--json stays parseable)
    redirect = contextlib.redirect_stdout(sys.stderr) if describe else contextlib.nullcontext()
    try:
        with redirect:
            runpy.run_path(str(script_path), run_name="__main__")
    except _StopScript:
        run.stopped_early = True
    except SystemExit as exc:
        code = exc.code
        run.exit_code = code if isinstance(code, int) else (0 if code is None else 1)
        if run.exit_code and not isinstance(code, int):
            run.error = str(code)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - any error of the user script is reported, not raised
        run.exit_code = 1
        run.error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    finally:
        sys.argv = saved_argv
        sys.path[:] = saved_path
        set_snapshot_hook(previous_hook)
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        try:
            matplotlib.use(saved_mpl_backend, force=True)
        except Exception:  # noqa: BLE001 - the original backend may not be importable here
            pass
        if scratch is not None:
            scratch.cleanup()
    return run
