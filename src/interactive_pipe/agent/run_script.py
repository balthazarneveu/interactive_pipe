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
import signal
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
    results: Any = None  # what the call returned (the outputs shown in the PNG)


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
        output = self.output.replace("{name}", name)  # then the folder rule, as for the variable
        base = Path(output) / f"{name}.png" if _is_folder(output) else Path(output)
        if not base.suffix:
            base = base.with_suffix(".png")
        candidate, index = base, 2
        while candidate in self.used:
            candidate = base.with_name(f"{base.stem}_{index}{base.suffix}")
            index += 1
        self.used.add(candidate)
        return candidate


def _forget_script_modules(before: set, folder: Path) -> None:
    """Drop the modules the script imported from its own folder (its siblings),
    so another script run in this process imports its own ``helpers.py``."""
    for name in set(sys.modules) - before:
        module_file = getattr(sys.modules.get(name), "__file__", None)
        if module_file and Path(module_file).resolve().parent == folder:
            del sys.modules[name]


def _intercept_interact(hook: Callable[..., Any]) -> Any:
    """``@interact`` / ``interact(...)(f)`` open their window at decoration time and
    ignore INTERACTIVE_PIPE_SNAPSHOT: give them a GUI class whose ``run`` goes
    through the snapshot hook instead (the event loop would never return here).
    Returns what ``_restore_interact`` needs."""
    from interactive_pipe.graphical.gui import InteractivePipeGUI
    from interactive_pipe.headless.explore import snapshot_instead_of_gui
    from interactive_pipe.helper import filter_decorator

    original = getattr(filter_decorator, "get_interactive_pipeline_class", None)
    if original is None:  # renamed: nothing to intercept
        return None

    class InteractSnapshotGUI(InteractivePipeGUI):
        def init_app(self, **kwargs: Any) -> None:
            pass

        def run(self) -> list:
            filters = getattr(self.pipeline, "filters", None) or []
            name = self.name or (filters[0].name if filters else "interact")
            # inputs were set by __call__: the render reuses them
            return hook(name, self.pipeline, lambda path: snapshot_instead_of_gui(self.pipeline, path))

        def close(self) -> None:
            pass

    setattr(filter_decorator, "get_interactive_pipeline_class", lambda *args, **kwargs: InteractSnapshotGUI)
    return original


def _restore_interact(original: Any) -> None:
    if original is not None:
        from interactive_pipe.helper import filter_decorator

        setattr(filter_decorator, "get_interactive_pipeline_class", original)


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
    else:  # absolute now: the script may chdir before calling its pipelines
        trailing = output.endswith(("/", os.sep))
        output = os.path.abspath(output) + (os.sep if trailing else "")
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
        call = PipelineCall(name=name, path=None if describe else path, results=results)
        if describe:
            call.description = pipeline.describe()
            call.summary = pipeline.summary()
        run.calls.append(call)
        if len(run.calls) >= max_calls:
            raise _StopScript()
        return results

    saved_argv, saved_path = sys.argv, list(sys.path)
    saved_modules = set(sys.modules)
    # the Qt backend resets SIGINT / SIGTERM to SIG_DFL when it is selected
    saved_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    saved_interact_gui = _intercept_interact(hook)
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
        _forget_script_modules(saved_modules, script_path.parent)
        for sig, handler in saved_signals.items():
            if handler is not None:
                signal.signal(sig, handler)
        _restore_interact(saved_interact_gui)
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
