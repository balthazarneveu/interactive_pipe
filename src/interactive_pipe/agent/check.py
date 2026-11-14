"""``interactive-pipe check SCRIPT.py``: the one command a coding agent runs after an edit.

The script runs unmodified, without a window (as for ``snapshot``); every
pipeline it calls runs once with the values of that call, every pipeline it
only builds runs once with its defaults when it takes no input. The report fits
one screen and is stable (no timing, no temporary path)::

    check demo.py: OK - 1 pipeline, 0 errors, 1 warning
    pipeline 'process' (inputs: img)
      controls: gain = 1 slider(float) in [0, 2]
      outputs : img  (64, 64, 3) float64 [0, 1]
                out  (64, 64, 3) float64 [0, 2]
    warning: output 'out' is clipped: ...

Errors carry the file and line of the user's code. Exit code: 1 when anything
failed, 2 for a command-line option the pipeline rejects, else 0 (warnings do
not fail).
"""

import os
from typing import Any, Dict, List, Optional

import numpy as np

from interactive_pipe.agent.run_script import PipelineCall, ScriptRun, error_location

# logged by the snapshot machinery about the environment, not about the script
_ENVIRONMENT_WARNINGS = ("GUI not built", "GUI object not built")


def _short_path(path: str) -> str:
    """Path relative to the working directory when it is below it (stable output)."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # another drive (Windows)
        return path
    return path if relative.startswith("..") else relative


def _number(value: Any) -> Any:
    value = value.item() if isinstance(value, np.generic) else value
    if isinstance(value, float):
        return float(f"{value:.4g}")
    return value


def describe_value(value: Any) -> Dict[str, Any]:
    """Type, shape, dtype and value range of one output (JSON-friendly)."""
    from interactive_pipe.data_objects.image import Image

    entry: Dict[str, Any] = {}
    if isinstance(value, Image) and isinstance(getattr(value, "data", None), np.ndarray):
        entry["type"] = "Image"
        value = value.data
    if isinstance(value, np.ndarray):
        entry.setdefault("type", "array")
        entry.update(shape=list(value.shape), dtype=str(value.dtype))
        if value.size and (np.issubdtype(value.dtype, np.number) or value.dtype == bool):
            if not np.iscomplexobj(value):
                finite = value[np.isfinite(value)] if np.issubdtype(value.dtype, np.floating) else value
                if finite.size:
                    entry.update(min=_number(finite.min()), max=_number(finite.max()))
                if finite.size != value.size:
                    entry["non_finite"] = int(value.size - finite.size)
        return entry
    if value is None:
        return {"type": "None"}
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    module = type(value).__module__.split(".")[0]
    name = type(value).__name__
    return {"type": name if module in ("builtins", "interactive_pipe") else f"{module}.{name}"}


def _value_text(entry: Dict[str, Any]) -> str:
    if "shape" in entry:
        text = f"({', '.join(str(size) for size in entry['shape'])}{',' if len(entry['shape']) == 1 else ''}) "
        text += entry["dtype"]
        if entry["type"] == "Image":
            text = "Image " + text
        if "min" in entry:
            low, high = (str(val) if isinstance(val, bool) else f"{val:g}" for val in (entry["min"], entry["max"]))
            text += f" [{low}, {high}]"
        if "non_finite" in entry:
            text += f" ({entry['non_finite']} NaN/inf)"
        return text
    if entry["type"] == "str":
        return f"str ({entry['length']} characters)"
    return entry["type"]


def _control_entry(control: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("name", "kind", "type", "value", "range", "choices", "on")
    return {key: control[key] for key in keep if key in control}


def _control_text(control: Dict[str, Any]) -> str:
    from interactive_pipe.headless.snapshot import format_value

    text = f"{control['name']} = {format_value(control['value'])} {control['kind']}"
    if control["kind"] in ("point", "region"):
        text += " on " + (repr(control["on"]) if control.get("on") is not None else "the first image")
    elif control["kind"] not in ("checkbox", "dropdown", "text"):
        text += f"({control['type']})"
    if "range" in control:
        text += f" in [{format_value(control['range'][0])}, {format_value(control['range'][1])}]"
    if "choices" in control:
        text += " in {" + ", ".join(str(choice) for choice in control["choices"]) + "}"
    return text


def _error_entry(exc: BaseException, pipeline: Optional[str]) -> Dict[str, Any]:
    from interactive_pipe.core.engine import FilterError
    from interactive_pipe.core.graph import PipelineSyntaxError

    if isinstance(exc, FilterError):
        original = exc.original_error
        message = f"filter {exc.filter_name!r} raised {type(original).__name__}: {original}"
        if exc.hint:
            message += f" ({' '.join(line.strip() for line in exc.hint.splitlines() if line.strip())})"
    elif isinstance(exc, PipelineSyntaxError):  # the location is given separately
        message = f"PipelineSyntaxError in pipeline {exc.pipeline_name!r}: {exc.reason}"
        if exc.source_line:
            message += f"\n    {exc.source_line.strip()}"
        if exc.hint:
            message += f"\n    Hint: {exc.hint}"
    else:
        message = f"{type(exc).__name__}: {exc}".strip()
    entry: Dict[str, Any] = {"pipeline": pipeline, "type": type(exc).__name__, "message": message}
    location = error_location(exc)
    if location is not None:
        entry.update(file=_short_path(location[0]), line=location[1])
    return entry


def _call_entry(call: PipelineCall) -> Dict[str, Any]:
    pipeline = call.pipeline
    entry: Dict[str, Any] = {"name": call.name, "called": call.called}
    try:
        description = pipeline.describe()
    except Exception as exc:  # noqa: BLE001 - e.g. a pointer control aimed at an unknown output
        description = {"inputs": list(pipeline.inputs_routing or []), "controls": []}
        entry["describe_error"] = str(exc)
    entry["inputs"] = description["inputs"]
    entry["controls"] = [_control_entry(control) for control in description["controls"]]
    if call.outputs is not None:
        entry["outputs"] = [{"name": name, **describe_value(value)} for name, value in call.outputs]
        entry["status"] = "error" if call.failed else "ok"
    elif call.failed:
        entry["status"] = "error"
    else:
        entry["status"] = "not run"
        if not call.called and entry["inputs"]:
            entry["reason"] = (
                f"built but not called by the script (needs inputs: {', '.join(map(str, entry['inputs']))})"
            )
    return entry


def check_report(run: ScriptRun) -> Dict[str, Any]:
    """The ``check`` report as a JSON-friendly dict (``--json`` prints it)."""
    from interactive_pipe.headless.output_check import output_problems

    errors: List[Dict[str, Any]] = []
    problems: List[str] = []
    pipelines: List[Dict[str, Any]] = []
    seen = set()
    for call in run.calls:
        if call.failed:
            errors.append(_error_entry(call.error, call.name))  # type: ignore[arg-type]
        if call.outputs is not None:
            for message in output_problems(call.outputs, call.styles):
                if message not in problems:
                    problems.append(message)
        if call.name in seen:
            continue
        seen.add(call.name)
        pipelines.append(_call_entry(call))
    if run.usage_error:
        errors.append({"pipeline": None, "type": "usage", "message": run.usage_error})
    elif run.exception is not None and not any(call.error is run.exception for call in run.calls):
        errors.append(_error_entry(run.exception, None))
    elif run.exit_code and run.exception is None:
        errors.append({"pipeline": None, "type": "SystemExit", "message": run.error or f"exit code {run.exit_code}"})
    logged = [
        message
        for message in run.warnings
        if not any(problem in message for problem in problems)
        and not any(marker in message for marker in _ENVIRONMENT_WARNINGS)
    ]
    warnings_list = list(dict.fromkeys(problems + logged))
    if not pipelines and not errors:
        errors.append(
            {
                "pipeline": None,
                "type": "no pipeline",
                "message": "the script neither called nor defined a pipeline (@interactive_pipeline)",
            }
        )
    exit_code = 2 if run.usage_error else (1 if errors else 0)
    return {
        "script": _short_path(str(run.script)),
        "ok": not errors,
        "exit_code": exit_code,
        "pipelines": pipelines,
        "errors": errors,
        "warnings": warnings_list,
        "stopped_early": run.stopped_early,
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def format_check(report: Dict[str, Any]) -> str:
    """One screen of text: status line, then each pipeline, errors and warnings."""
    status = "OK" if report["ok"] else "FAILED"
    lines = [
        f"check {report['script']}: {status} - {_plural(len(report['pipelines']), 'pipeline')}, "
        f"{_plural(len(report['errors']), 'error')}, {_plural(len(report['warnings']), 'warning')}"
    ]
    for pipeline in report["pipelines"]:
        inputs = ", ".join(str(name) for name in pipeline["inputs"]) or "none"
        lines.append(f"pipeline {pipeline['name']!r} (inputs: {inputs})")
        controls = [_control_text(control) for control in pipeline["controls"]] or ["none"]
        lines.append(f"  controls: {controls[0]}")
        lines.extend(f"            {text}" for text in controls[1:])
        if "outputs" in pipeline:
            width = max([len(str(out["name"])) for out in pipeline["outputs"]] or [0])
            texts = [f"{str(out['name']):<{width}}  {_value_text(out)}" for out in pipeline["outputs"]] or ["none"]
            lines.append(f"  outputs : {texts[0]}")
            lines.extend(f"            {text}" for text in texts[1:])
        else:
            lines.append(f"  outputs : not run ({pipeline.get('reason', pipeline['status'])})")
    for error in report["errors"]:
        where = f"{error['file']}:{error['line']}: " if "file" in error else ""
        owner = f"pipeline {error['pipeline']!r}: " if error.get("pipeline") else ""
        lines.append(f"error: {where}{owner}{error['message']}")
    lines.extend(f"warning: {message}" for message in report["warnings"])
    if report["stopped_early"]:
        lines.append("note: the script was stopped after --max-calls pipeline calls")
    return "\n".join(lines)
