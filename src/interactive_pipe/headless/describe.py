"""Describe a pipeline as plain data: inputs, outputs, filters, controls.

``describe(pipeline)`` returns a JSON-serialisable dict (exposed as
``HeadlessPipeline.describe``); ``summary(pipeline)`` renders the same data as
readable text (``HeadlessPipeline.summary``). Together with ``snapshot`` and
``sweep`` this is what a coding agent needs to drive a pipeline without
seeing its window: which knobs exist, their ranges, and what comes out.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

from interactive_pipe.headless.control import CircularControl, Control, RangeControl, TextPrompt, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.panel import Panel
from interactive_pipe.headless.pointer import PointerControl, check_targets
from interactive_pipe.headless.snapshot import format_value

if TYPE_CHECKING:
    from interactive_pipe.headless.pipeline import HeadlessPipeline


def to_plain(value: Any) -> Any:
    """Convert a value to JSON-friendly Python types (numpy scalars, tuples,
    Panels, paths, arrays...)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return f"array{value.shape} {value.dtype}"
    if isinstance(value, dict):
        return {str(key): to_plain(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Panel):
        return value.name
    return repr(value)


def control_kind(ctrl: Control) -> str:
    """Widget family: keyboard, time, range, point, region, text, checkbox, dropdown, slider or number."""
    if isinstance(ctrl, PointerControl):
        return ctrl.kind
    if isinstance(ctrl, KeyboardControl):
        return "keyboard"
    if isinstance(ctrl, TimeControl):
        return "time"
    if isinstance(ctrl, RangeControl):
        return "range"
    if isinstance(ctrl, TextPrompt):
        return "text"
    if ctrl._type is bool:
        return "checkbox"
    if ctrl._type is str:
        return "dropdown" if ctrl.value_range is not None else "text"
    return "slider" if ctrl.value_range is not None else "number"


def _panel_path(panel: Any) -> List[str]:
    names = []
    while panel is not None:
        if panel.name:
            names.append(str(panel.name))
        panel = panel.parent
    return names[::-1]


def describe_control(ctrl: Control) -> Dict[str, Any]:
    """Plain description of one control."""
    kind = control_kind(ctrl)
    entry: Dict[str, Any] = {
        "name": ctrl.name,
        "filter": ctrl.filter_to_connect.name if ctrl.filter_to_connect is not None else None,
        "parameter": ctrl.parameter_name_to_connect,
        "kind": kind,
        "type": ctrl._type.__name__ if ctrl._type is not None else None,
        "default": to_plain(ctrl.value_default),
        "value": to_plain(ctrl.value),
    }
    if isinstance(ctrl, PointerControl):
        # fractions of the target image size; on=None: the first image output
        entry["on"] = ctrl.on
        entry["axes"] = list(ctrl.axes)
    elif ctrl.value_range is not None:
        if ctrl._type is str:
            entry["choices"] = to_plain(ctrl.value_range)
        else:
            entry["range"] = to_plain(ctrl.value_range)
    if ctrl.step is not None and kind not in ("checkbox", "text"):
        entry["step"] = to_plain(ctrl.step)
    if isinstance(ctrl, CircularControl):
        entry["circular"] = True
    if ctrl.panel is not None:
        entry["group"] = to_plain(ctrl.panel.name)
        path = _panel_path(ctrl.panel)
        if len(path) > 1:
            entry["panel_path"] = path
    keys: Dict[str, Any] = {}
    if isinstance(ctrl, KeyboardControl):
        keys = {"keydown": ctrl.keydown, "keyup": ctrl.keyup, "modulo": ctrl.modulo}
    elif isinstance(ctrl, TimeControl):
        keys = {"pause_resume": ctrl.pause_resume_key}
        entry["update_interval_ms"] = ctrl.update_interval_ms
    keys = {key: val for key, val in keys.items() if val is not None}
    if keys:
        entry["keys"] = keys
    if ctrl.tooltip:
        entry["tooltip"] = ctrl.tooltip
    return entry


def _doc_line(func: Any) -> Optional[str]:
    doc = getattr(func, "__doc__", None)
    if not doc:
        return None
    for line in doc.strip().splitlines():
        if line.strip():
            return line.strip()
    return None


def describe(pipeline: "HeadlessPipeline") -> Dict[str, Any]:
    """Describe the pipeline as a JSON-serialisable dict.

    Keys:
        name: pipeline name.
        inputs: input names, in call order.
        outputs: output layout (flat list = one row, list of lists = grid,
            None = empty cell).
        filters: in execution order, each with its input / output variable
            names, current parameter values, control names and docstring line.
        controls: name, owning filter, parameter, kind (slider / number /
            checkbox / dropdown / range / text / time / keyboard / point /
            region, with ``on``: the target output, None for the first
            image), type,
            default, current value, range or choices, step, group, key
            bindings and tooltip when present.

    Example:
        ```python
        import json

        print(json.dumps(pipe.describe(), indent=2))
        print(pipe.summary())  # the same, as text
        ```
    """
    controls = list(getattr(pipeline, "controls", None) or [])
    check_targets(pipeline)
    controls_by_filter: Dict[str, List[str]] = {}
    for ctrl in controls:
        if ctrl.filter_to_connect is not None:
            controls_by_filter.setdefault(ctrl.filter_to_connect.name, []).append(ctrl.name)
    filters = []
    for filt in pipeline.filters:
        entry: Dict[str, Any] = {
            "name": filt.name,
            "inputs": to_plain(filt.inputs),
            "outputs": to_plain(filt.outputs),
            "parameters": to_plain(dict(filt.values)),
            "controls": controls_by_filter.get(filt.name, []),
        }
        doc = _doc_line(getattr(filt, "apply", None))
        if doc:
            entry["doc"] = doc
        filters.append(entry)
    return {
        "name": to_plain(pipeline.name),
        "inputs": to_plain(list(pipeline.inputs_routing or [])),
        "outputs": to_plain(pipeline.outputs),
        "filters": filters,
        "controls": [describe_control(ctrl) for ctrl in controls],
    }


def _layout_text(outputs: Any) -> str:
    if not outputs:
        return "(none)"
    if isinstance(outputs[0], list):
        return " / ".join("[" + ", ".join("-" if out is None else str(out) for out in row) + "]" for row in outputs)
    return "[" + ", ".join(str(out) for out in outputs) + "]"


def _control_line(entry: Dict[str, Any], width: int) -> str:
    kind = entry["kind"] if entry["kind"] in ("checkbox", "dropdown", "text") else f"{entry['kind']}({entry['type']})"
    if entry["kind"] in ("point", "region"):
        kind = f"{entry['kind']}({', '.join(entry['axes'])} in [0, 1])"
    details = [kind, f"= {format_value(entry['value'])}"]
    if "axes" in entry:
        details.append("on " + (repr(entry["on"]) if entry["on"] is not None else "the first image"))
    if "range" in entry:
        details.append(f"in [{format_value(entry['range'][0])}, {format_value(entry['range'][1])}]")
    if "choices" in entry:
        details.append("in {" + ", ".join(str(choice) for choice in entry["choices"]) + "}")
    if "step" in entry and entry["kind"] in ("slider", "keyboard", "range"):
        details.append(f"step {format_value(entry['step'])}")
    if entry["default"] != entry["value"]:
        details.append(f"(default {format_value(entry['default'])})")
    if "keys" in entry:
        details.append("keys " + ", ".join(f"{key}={val!r}" for key, val in entry["keys"].items()))
    if "group" in entry:
        details.append(f"group {entry['group']!r}")
    target = f"{entry['filter']}.{entry['parameter']}" if entry["filter"] else "(not connected)"
    line = f"  {entry['name']:<{width}} " + " ".join(details) + f"  -> {target}"
    if "tooltip" in entry:
        line += f"  # {entry['tooltip']}"
    return line


def summary(pipeline: "HeadlessPipeline") -> str:
    """Readable text version of ``describe()`` (``print(pipe.summary())``)."""
    data = describe(pipeline)
    lines = [
        f"Pipeline {data['name']!r}",
        f"  inputs : {', '.join(str(name) for name in data['inputs']) or '(none)'}",
        f"  outputs: {_layout_text(data['outputs'])}",
        "Filters (execution order):",
    ]
    for filt in data["filters"]:
        inputs = ", ".join(str(name) for name in filt["inputs"] or [])
        outputs = ", ".join(str(name) for name in filt["outputs"] or [])
        params = ", ".join(f"{key}={format_value(val)}" for key, val in filt["parameters"].items())
        line = f"  {filt['name']}({inputs}) -> {outputs or '()'}"
        if params:
            line += f"   [{params}]"
        lines.append(line)
        if "doc" in filt:
            lines.append(f"      {filt['doc']}")
    lines.append("Controls:" if data["controls"] else "Controls: (none)")
    width = max([len(str(entry["name"])) for entry in data["controls"]] + [4])
    lines.extend(_control_line(entry, width) for entry in data["controls"])
    return "\n".join(lines)
