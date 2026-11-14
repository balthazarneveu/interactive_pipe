"""Run an unmodified user script without opening any window.

Used by ``interactive-pipe snapshot``, ``sweep``, ``describe`` and ``check``.
The script runs in this process as ``__main__`` (so pipelines called under
``if __name__ == "__main__":`` are reached), with ``INTERACTIVE_PIPE_SNAPSHOT``
set and a snapshot hook (``interactive_pipe.cli.set_snapshot_hook``) that sees
every call of a GUI-decorated pipeline.

Each call is first let through until the pipeline is about to run (the
script's inputs and keyword arguments are then set; ``--set`` values are
applied on top); the command then renders it with its own options
(``run_snapshot`` / ``sweep`` of ``headless.explore``), so the script's call
values and the command-line values combine as in ``pipe.snapshot(path, **values)``.

Several pipelines, several calls: every call writes its own PNG, named after
the pipeline (``<folder>/<pipeline>.png``, then ``<pipeline>_2.png`` ... when the
same pipeline is called again; with a file name ``out.png``: ``out.png``,
``out_2.png`` ...). After ``max_calls`` calls the script is stopped, so a script
looping over a dataset does not run forever.
"""

import contextlib
import dataclasses
import inspect
import io
import logging
import os
import runpy
import signal
import sys
import tempfile
import traceback
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

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
    error: Optional[BaseException] = None  # what the call raised (FilterError, DisplayError...)
    pipeline: Any = None  # the HeadlessPipeline behind the call
    outputs: Optional[List[Tuple[str, Any]]] = None  # (name, raw value) of the run, when observed
    styles: Dict[str, Any] = field(default_factory=dict)  # layout.style options of the run
    called: bool = True  # False: built by the script, not called through a GUI (check only)

    @property
    def failed(self) -> bool:
        return self.error is not None


@dataclass
class ScriptRun:
    """What happened while running the script."""

    script: Path
    calls: List[PipelineCall] = field(default_factory=list)
    exit_code: int = 0
    error: Optional[str] = None  # the script's error, formatted once (see format_script_error)
    exception: Optional[BaseException] = None
    stopped_early: bool = False
    usage_error: Optional[str] = None  # a command-line option the pipeline rejects (exit code 2)
    warnings: List[str] = field(default_factory=list)  # captured by check
    skipped: List[str] = field(default_factory=list)  # pipelines left out by --pipeline
    namespace: Dict[str, Any] = field(default_factory=dict)  # the script's globals

    @property
    def written(self) -> List[Path]:
        return [call.path for call in self.calls if call.path is not None and not call.failed and call.called]

    @property
    def failed_calls(self) -> List[PipelineCall]:
        return [call for call in self.calls if call.failed]


_RUNPY_FILE = os.path.abspath(runpy.__file__)


def _package_dir() -> str:
    import interactive_pipe

    return os.path.dirname(os.path.abspath(interactive_pipe.__file__)) + os.sep


def _library_dirs() -> Tuple[str, ...]:
    """interactive_pipe, the standard library and the installed packages."""
    import sysconfig

    paths = sysconfig.get_paths()
    folders = {paths.get(key) for key in ("stdlib", "platstdlib", "purelib", "platlib")}
    return (_package_dir(), *(os.path.abspath(folder) + os.sep for folder in folders if folder))


def _is_user_frame(filename: str) -> bool:
    """Frames of the user's code: not interactive_pipe, the standard library (runpy...) nor installed packages."""
    if filename.startswith("<"):
        return False
    path = os.path.abspath(filename)
    return path != _RUNPY_FILE and not path.startswith(_library_dirs())


def error_location(exc: BaseException) -> Optional[Tuple[str, int]]:
    """(file, line) of the user code an error points to, None when unknown.

    ``PipelineSyntaxError``: the offending pipeline line; ``FilterError``: the
    innermost frame of the filter; anything else: the innermost frame outside
    interactive_pipe."""
    from interactive_pipe.core.engine import FilterError
    from interactive_pipe.core.graph import PipelineSyntaxError

    if isinstance(exc, PipelineSyntaxError) and exc.filename is not None and exc.lineno is not None:
        return exc.filename, exc.lineno
    if isinstance(exc, FilterError):
        frames = getattr(exc, "_user_frames", None) or []
        if frames:
            return frames[-1].filename, frames[-1].lineno or 0
    frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if _is_user_frame(frame.filename)]
    if frames:
        return frames[-1].filename, frames[-1].lineno or 0
    return None


def format_script_error(exc: BaseException) -> str:
    """The script's error, printed once and without interactive_pipe's own frames.

    ``FilterError`` and ``PipelineSyntaxError`` messages already name the
    user's file and line: only the call site in the script is added. Other
    errors get a traceback of the user's frames."""
    from interactive_pipe.core.engine import FilterError
    from interactive_pipe.core.graph import PipelineSyntaxError

    user_frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if _is_user_frame(frame.filename)]
    message = "".join(traceback.format_exception_only(type(exc), exc)).rstrip()
    if isinstance(exc, (FilterError, PipelineSyntaxError)):
        user_frames = user_frames[-1:]  # where the script called / decorated the pipeline
    lines = ["Traceback (user code only):", *traceback.format_list(user_frames)] if user_frames else []
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines) + message


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


class _Scratch:
    """Temporary folder for the renders nobody keeps, created on first use."""

    def __init__(self) -> None:
        self._directory: Optional[tempfile.TemporaryDirectory] = None
        self._chooser: Optional[_PathChooser] = None

    def folder(self) -> Path:
        if self._directory is None:
            self._directory = tempfile.TemporaryDirectory(prefix="interactive_pipe_run_")
        return Path(self._directory.name)

    def path(self, name: str) -> Path:
        if self._chooser is None:
            self._chooser = _PathChooser(f"{self.folder().as_posix()}/scratch/")
        return self._chooser(name)

    def cleanup(self) -> None:
        if self._directory is not None:
            self._directory.cleanup()


class _Prepared(Exception):
    """Raised by the wrapped ``pipeline.run`` once the inputs and parameters of
    the script's call are known: the CLI then renders with its own options."""


class CommandLineError(Exception):
    """A command-line option the script's pipeline cannot accept (unknown name, bad value)."""


def _named_outputs(outputs: Any, result: Any) -> List[Tuple[str, Any]]:
    """(output name, value) pairs of one run, in reading order, empty cells skipped."""
    if result is None:
        return []
    if outputs is None:
        outputs = []
    if isinstance(result, list) and result and isinstance(result[0], list):  # 2D layout
        names = [name for row in outputs for name in (row if isinstance(row, (list, tuple)) else [row])]
        values = [value for row in result for value in row]
    else:
        names = list(outputs)
        values = list(result) if isinstance(result, (tuple, list)) else [result]
    pairs = []
    for index, value in enumerate(values):
        name = names[index] if index < len(names) else index
        if name is None:
            continue
        pairs.append((str(name), value))
    return pairs


def _filter_values(pipeline: Any) -> Dict[Tuple[str, str], Any]:
    return {(filt.name, key): value for filt in pipeline.filters for key, value in filt.values.items()}


def _differs(left: Any, right: Any) -> bool:
    try:
        return bool(left != right)
    except (TypeError, ValueError):  # numpy arrays
        return left is not right


@contextlib.contextmanager
def _wrapped_run(pipeline: Any, before: Callable[[], None], after: Callable[[Any], None]) -> Any:
    """Temporarily replace ``pipeline.run`` (instance attribute) by ``before(); run(); after(result)``."""
    original = pipeline.run

    def run() -> Any:
        before()
        result = original()
        after(result)
        return result

    pipeline.run = run
    try:
        yield
    finally:
        try:
            del pipeline.run
        except AttributeError:  # pragma: no cover - run was already an instance attribute
            pipeline.run = original


@dataclass
class CallOptions:
    """What the command line asks for each captured pipeline call."""

    mode: str = "snapshot"  # snapshot / describe / sweep / check
    settings: Dict[str, str] = field(default_factory=dict)  # --set NAME=VALUE (raw text)
    axes: Dict[str, List[str]] = field(default_factory=dict)  # --param NAME=V1,V2 (raw text)
    steps: Dict[str, int] = field(default_factory=dict)  # --steps NAME=N
    output: Optional[str] = None  # --output NAME[,NAME] / index / all
    pipeline: Optional[str] = None  # --pipeline NAME: only this one


def _names_for(pipeline: Any, names: Sequence[str], namespace: Dict[str, Any]) -> List[str]:
    """The names to apply to this pipeline: a name this pipeline does not have but
    another pipeline of the script has is meant for that one (skipped here); a name
    no pipeline has stays, so that the resolver rejects it with its suggestions."""
    from interactive_pipe.headless.explore import parameter_targets

    known = parameter_targets(pipeline)
    others = [other for other in found_pipelines(namespace).values() if other is not pipeline]
    return [name for name in names if name in known or not any(name in parameter_targets(other) for other in others)]


def _local_options(pipeline: Any, options: CallOptions, namespace: Dict[str, Any]) -> Optional[CallOptions]:
    """``options`` restricted to the names of this pipeline (see ``_names_for``);
    None for a sweep left with nothing to sweep (its parameters belong to another pipeline)."""
    settings = {name: options.settings[name] for name in _names_for(pipeline, list(options.settings), namespace)}
    axes = {name: options.axes[name] for name in _names_for(pipeline, list(options.axes), namespace)}
    steps = {name: options.steps[name] for name in _names_for(pipeline, list(options.steps), namespace)}
    if options.mode == "sweep" and not axes and not steps:
        return None
    return dataclasses.replace(options, settings=settings, axes=axes, steps=steps)


def _prepare(pipeline: Any, render: Callable[[Path], Any], scratch: Path, options: CallOptions) -> Dict[str, Any]:
    """Let the script's call set the inputs, then stop before running: returns
    the parameter values of that call (script keyword arguments and ``--set``
    values) as ``{"filter.parameter": value}`` overrides."""
    from interactive_pipe.agent.parameters import typed_settings
    from interactive_pipe.headless.explore import apply_overrides

    settings = typed_settings(pipeline, options.settings)
    captured: Dict[Tuple[str, str], Any] = {}

    def before() -> None:
        try:
            apply_overrides(pipeline, settings, "--set")
        except (TypeError, ValueError) as exc:
            raise CommandLineError(str(exc)) from None
        pipeline.update_parameters_from_controls()
        captured.update(_filter_values(pipeline))
        raise _Prepared()

    with _wrapped_run(pipeline, before, lambda result: None):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                render(scratch)
        except _Prepared:
            pass
    current = _filter_values(pipeline)
    return {
        f"{filter_name}.{param}": value
        for (filter_name, param), value in captured.items()
        if (filter_name, param) not in current or _differs(current[(filter_name, param)], value)
    }


def _observe(pipeline: Any, call: "PipelineCall") -> Any:
    """Wrap ``pipeline.run`` to record the named raw outputs and styles of the run."""

    def after(result: Any) -> None:
        call.outputs = _named_outputs(getattr(pipeline, "outputs", None), result)
        framework_state = getattr(pipeline, "framework_state", None)
        call.styles = dict(framework_state.output_styles) if framework_state is not None else {}

    return _wrapped_run(pipeline, lambda: None, after)


def _as_script_results(result: Any) -> Any:
    # what a GUI call returns (see headless.explore.snapshot_instead_of_gui)
    if result is None:
        return []
    return list(result) if isinstance(result, tuple) else result


def _render_call(pipeline: Any, call: "PipelineCall", path: Path, fixed: Dict[str, Any], options: CallOptions) -> Any:
    """Render one captured call as the mode asks; returns what the script's call returns."""
    from interactive_pipe.agent.parameters import check_step_names, output_selector, typed_axes
    from interactive_pipe.headless.explore import run_snapshot

    selector = output_selector(options.output)
    if options.mode == "sweep":
        axes = typed_axes(pipeline, options.axes)
        check_step_names(pipeline, options.steps)
        swept = {target for name in [*axes, *options.steps] for target in _targets(pipeline, name)}
        fixed = {name: value for name, value in fixed.items() if tuple(name.split(".", 1)) not in swept}
        try:
            pipeline.sweep(path, params={**fixed, **axes}, steps=options.steps or None, output=selector)
        except (TypeError, ValueError) as exc:
            if type(exc).__name__ in ("FilterError", "DisplayError", "PipelineSyntaxError"):
                raise
            raise CommandLineError(str(exc)) from None
        print(f"interactive_pipe: sweep of {pipeline.name!r} written to {path}")
        return []
    with _observe(pipeline, call):
        if options.mode == "snapshot":
            try:
                written, result = run_snapshot(pipeline, path, params=fixed, output=selector)
            except (TypeError, ValueError) as exc:
                if type(exc).__name__ in ("FilterError", "DisplayError") or selector is None:
                    raise
                raise CommandLineError(str(exc)) from None
            print(f"interactive_pipe: snapshot of {pipeline.name!r} written to {written}")
        else:  # describe / check: rendered in a scratch folder (also checks the outputs can be displayed)
            with contextlib.redirect_stdout(io.StringIO()):
                _, result = run_snapshot(pipeline, path, params=fixed)
    return _as_script_results(result)


def _targets(pipeline: Any, name: str) -> List[Tuple[str, str]]:
    from interactive_pipe.headless.explore import parameter_targets

    return parameter_targets(pipeline).get(name, [])


class _Capture(logging.Handler):
    """Warnings logged while the script runs (``check``)."""

    def __init__(self, messages: List[str]):
        super().__init__(logging.WARNING)
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextlib.contextmanager
def _captured_warnings(messages: List[str]) -> Any:
    """Collect ``logging`` warnings and ``warnings.warn`` messages into ``messages``."""
    handler = _Capture(messages)
    root = logging.getLogger()
    root.addHandler(handler)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            yield
        finally:
            root.removeHandler(handler)
            messages.extend(str(item.message) for item in caught)


def run_script(
    script: str,
    script_args: Sequence[str] = (),
    output: Optional[str] = None,
    describe: bool = False,
    max_calls: int = DEFAULT_MAX_CALLS,
    options: Optional[CallOptions] = None,
) -> ScriptRun:
    """Run `script` headless; every GUI-decorated pipeline call writes a PNG.

    Args:
        script: Path of the python script.
        script_args: Its command line arguments (``sys.argv[1:]``).
        output: PNG file, folder, or pattern with ``{name}``; defaults to
            ``default_output(script)``. Ignored by ``describe`` and ``check``.
        describe: Same as ``options=CallOptions(mode="describe")``.
        max_calls: Stop the script after this many pipeline calls.
        options: What to do with each call: ``mode`` ``"snapshot"`` (default),
            ``"sweep"`` (``axes`` / ``steps``), ``"describe"`` (record
            ``describe()`` / ``summary()``) or ``"check"`` (record the outputs
            and the warnings, see ``interactive_pipe.agent.check``); ``--set``
            values, the output to show, one pipeline only.

    Raises:
        FileNotFoundError: If the script does not exist.
        ValueError: If ``max_calls`` is not positive.
    """
    from interactive_pipe.cli import SNAPSHOT_ENV_VAR, set_snapshot_hook

    options = options if options is not None else CallOptions()
    if describe:
        options.mode = "describe"
    keep_pngs = options.mode in ("snapshot", "sweep")
    script_path = Path(script).resolve()
    if not script_path.is_file():
        raise FileNotFoundError(f"script not found: {script}")
    if max_calls < 1:
        raise ValueError(f"max_calls should be at least 1, got {max_calls}")
    scratch = _Scratch()
    if not keep_pngs:
        output = f"{scratch.folder().as_posix()}/"
    elif output is None:
        output = f"{default_output(script_path).as_posix()}/"
    else:  # absolute now: the script may chdir before calling its pipelines
        trailing = output.endswith(("/", os.sep))
        output = os.path.abspath(output) + (os.sep if trailing else "")
    run = ScriptRun(script=script_path)
    choose_path = _PathChooser(output)
    scratch_paths = scratch.path

    def hook(name: str, pipeline: Any, render: Callable[[Path], Any]) -> Any:
        local = _local_options(pipeline, options, run.namespace)
        if (options.pipeline is not None and name != options.pipeline) or local is None:
            run.skipped.append(name)
            with contextlib.redirect_stdout(io.StringIO()):
                return render(scratch_paths(name))  # not asked for: the script still gets its results
        path = choose_path(f"{name}_sweep" if options.mode == "sweep" else name)
        path.parent.mkdir(parents=True, exist_ok=True)
        call = PipelineCall(name=name, path=path if keep_pngs else None, pipeline=pipeline)
        run.calls.append(call)
        if options.mode == "describe":  # also when the run fails: the controls are known before running
            call.description = pipeline.describe()
            call.summary = pipeline.summary()
        from interactive_pipe.agent.parameters import ParameterError

        try:
            fixed = _prepare(pipeline, render, scratch_paths(name), local)
            call.results = _render_call(pipeline, call, path, fixed, local)
        except (CommandLineError, ParameterError) as exc:
            run.calls.remove(call)  # nothing was rendered
            run.usage_error = str(exc)
            raise _StopScript() from None
        except Exception as exc:
            call.error = exc  # the script decides: it usually stops with this error
            raise
        if len(run.calls) >= max_calls:
            run.stopped_early = True
            raise _StopScript()
        return call.results

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
    # describe / check: the script's own prints go to stderr, stdout is the report (--json stays parseable)
    quiet = options.mode in ("describe", "check")
    redirect = contextlib.redirect_stdout(sys.stderr) if quiet else contextlib.nullcontext()
    capture = _captured_warnings(run.warnings) if options.mode == "check" else contextlib.nullcontext()
    try:
        with redirect, capture:
            try:
                _exec_as_main_into(script_path, run)
            except _StopScript:
                pass
            except SystemExit as exc:
                code = exc.code
                run.exit_code = code if isinstance(code, int) else (0 if code is None else 1)
                if run.exit_code and not isinstance(code, int):
                    run.error = str(code)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:  # noqa: BLE001 - any error of the user script is reported, not raised
                run.exit_code = 1
                run.exception = exc
                run.error = format_script_error(exc)
            if options.mode == "check" and run.usage_error is None:
                _run_uncalled_pipelines(run, scratch_paths)
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
        scratch.cleanup()
    return run


def _exec_as_main_into(script_path: Path, run: ScriptRun) -> None:
    """``_exec_as_main`` keeping the namespace on ``run`` even when the script raises."""
    import builtins
    import types

    module = types.ModuleType("__main__")
    module.__dict__.update(__file__=str(script_path), __builtins__=builtins, __loader__=None, __package__=None)
    module.__dict__.update(__spec__=None, __cached__=None)
    run.namespace = module.__dict__
    code = compile(script_path.read_bytes(), str(script_path), "exec")
    saved_main = sys.modules.get("__main__")
    sys.modules["__main__"] = module
    try:
        exec(code, module.__dict__)
    finally:
        if saved_main is not None:
            sys.modules["__main__"] = saved_main


def found_pipelines(namespace: Dict[str, Any]) -> Dict[str, Any]:
    """Pipelines defined (or imported) by the script: ``{name: HeadlessPipeline}``,
    GUI-decorated functions included (their headless pipeline)."""
    from interactive_pipe.headless.pipeline import HeadlessPipeline

    found: Dict[str, Any] = {}
    for value in list(namespace.values()):
        pipeline = value
        if not isinstance(pipeline, HeadlessPipeline):
            if not inspect.isfunction(value):  # e.g. the context / layout proxies raise on any attribute
                continue
            pipeline = getattr(getattr(value, "describe", None), "__self__", None)
        if isinstance(pipeline, HeadlessPipeline) and pipeline.name not in found:
            found[str(pipeline.name)] = pipeline
    return found


def _run_uncalled_pipelines(run: ScriptRun, scratch_paths: Callable[[str], Path]) -> None:
    """``check``: pipelines the script built but did not call through a GUI. Those
    taking no input run once with their defaults; the others are listed."""
    called = {call.name for call in run.calls}
    for name, pipeline in found_pipelines(run.namespace).items():
        if name in called:
            continue
        call = PipelineCall(name=name, path=None, pipeline=pipeline, called=False)
        run.calls.append(call)
        if list(pipeline.inputs_routing or []):
            continue  # needs inputs the script did not give
        from interactive_pipe.headless.explore import run_snapshot

        try:
            with _observe(pipeline, call), contextlib.redirect_stdout(io.StringIO()):
                run_snapshot(pipeline, scratch_paths(name))
        except Exception as exc:  # noqa: BLE001 - reported by check
            call.error = exc
