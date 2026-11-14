"""Parameter values typed on the command line (``--set``, ``--param``, ``--steps``).

The names go through the library's resolver (``headless.explore.resolve_names``:
a parameter name, a control name or ``filter.parameter``, with the list of
available names and a close match on a typo); the text values are converted
to the type of the control driving the parameter (``describe()`` gives its
kind and type), or to the type of the parameter's current value when no
control drives it.

Value syntax:

- numbers: ``gain=2``, ``gain=0.5``; checkboxes: ``true/false``, ``1/0``,
  ``yes/no``, ``on/off``; dropdowns and text: the text itself (``mode=dark``);
- ranges, points and regions: comma-separated numbers (``seed=0.2,0.4``,
  ``band=0.1,0.3``);
- swept values (``--param``): comma-separated (``gain=0.5,1,2``), or
  ``;``-separated for ranges / points / regions (``seed="0.1,0.1;0.6,0.4"``);
  repeating ``--param`` with the same name appends values.
"""

import ast
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: describe() kinds whose value is a tuple of numbers
TUPLE_KINDS = ("range", "point", "region")
_TRUE = ("true", "1", "yes", "on")
_FALSE = ("false", "0", "no", "off")


class ParameterError(ValueError):
    """A command-line parameter that names nothing or cannot be converted."""


def split_assignment(text: str, option: str) -> Tuple[str, str]:
    """``"gain=2"`` -> ``("gain", "2")``."""
    name, sep, value = text.partition("=")
    name = name.strip()
    if not sep or not name:
        raise ParameterError(f"{option} {text!r}: expected NAME=VALUE (e.g. {option} gain=2.0)")
    return name, value.strip()


def parse_assignments(texts: Optional[Sequence[str]], option: str) -> Dict[str, str]:
    """Repeated ``--set NAME=VALUE`` -> ``{name: raw value}`` (the last one wins)."""
    return dict(split_assignment(text, option) for text in texts or ())


def parse_sweep_assignments(texts: Optional[Sequence[str]], option: str = "--param") -> Dict[str, List[str]]:
    """Repeated ``--param NAME=V1,V2`` -> ``{name: [raw text of each --param]}`` (kept in order)."""
    axes: Dict[str, List[str]] = {}
    for text in texts or ():
        name, raw = split_assignment(text, option)
        axes.setdefault(name, []).append(raw)
    return axes


def parse_steps(texts: Optional[Sequence[str]]) -> Dict[str, int]:
    """Repeated ``--steps NAME=N`` -> ``{name: N}``."""
    steps: Dict[str, int] = {}
    for text in texts or ():
        name, raw = split_assignment(text, "--steps")
        try:
            count = int(raw)
        except ValueError:
            raise ParameterError(f"--steps {text!r}: the count should be an integer, e.g. --steps {name}=5") from None
        steps[name] = count
    return steps


def _value_spec(pipeline: Any, targets: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Kind, type and description of the control behind ``targets`` (from describe()),
    or the type of the current parameter value when no control drives it."""
    for entry in pipeline.describe()["controls"]:
        if (entry["filter"], entry["parameter"]) in targets:
            return entry
    values = {filt.name: filt.values for filt in pipeline.filters}
    filter_name, param_name = targets[0]
    current = values.get(filter_name, {}).get(param_name)
    return {"kind": None, "type": type(current).__name__ if current is not None else None, "value": current}


def _describe_spec(spec: Dict[str, Any]) -> str:
    if spec.get("kind") is None:
        return f"the parameter is a {spec['type']}" if spec.get("type") else "the parameter has no value yet"
    text = f"control {spec['name']!r} is a {spec['kind']} ({spec['type']})"
    if "range" in spec:
        text += f" in [{spec['range'][0]}, {spec['range'][1]}]"
    if "choices" in spec:
        text += f", choices: {', '.join(str(choice) for choice in spec['choices'])}"
    return text


def _number(raw: str, kind: str) -> Any:
    value = float(raw)
    if kind == "int":
        if not value.is_integer():
            raise ValueError(raw)
        return int(value)
    return value


def convert(raw: str, spec: Dict[str, Any], label: str) -> Any:
    """Convert one text value to the type described by ``spec`` (see ``_value_spec``)."""
    kind, type_name = spec.get("kind"), spec.get("type")
    try:
        if kind in TUPLE_KINDS or (kind is None and isinstance(spec.get("value"), tuple)):
            parts = [part.strip() for part in raw.strip("()[] ").split(",")]
            item_type = "int" if type_name == "int" else "float"
            if kind is None:  # a tuple parameter without control: the type of each item
                item_type = "int" if all(isinstance(item, int) for item in spec["value"]) else "float"
            return tuple(_number(part, item_type) for part in parts)
        if type_name == "bool":
            lowered = raw.lower()
            if lowered not in _TRUE + _FALSE:
                raise ValueError(raw)
            return lowered in _TRUE
        if type_name in ("int", "float"):
            return _number(raw, type_name)
        if type_name == "str":
            return raw
    except ValueError:
        expected = {"bool": "true or false", "int": "an integer", "float": "a number"}.get(
            str(type_name), "comma-separated numbers"
        )
        if kind in TUPLE_KINDS:
            expected = "comma-separated numbers, e.g. 0.2,0.4"
        raise ParameterError(f"{label}: {raw!r} is not {expected} ({_describe_spec(spec)})") from None
    try:  # unknown type: a python literal, else the text
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw


def _resolve(pipeline: Any, names: Sequence[str], option: str) -> Dict[str, List[Tuple[str, str]]]:
    from interactive_pipe.headless.explore import resolve_names

    try:
        return resolve_names(pipeline, list(names), caller=f"{option} (pipeline {pipeline.name!r})")
    except TypeError as exc:
        raise ParameterError(str(exc).replace("keyword argument(s)", "parameter name(s)")) from None


def typed_settings(pipeline: Any, settings: Dict[str, str], option: str = "--set") -> Dict[str, Any]:
    """``{name: raw text}`` -> ``{name: typed value}`` for this pipeline."""
    resolved = _resolve(pipeline, list(settings), option)
    return {
        name: convert(raw, _value_spec(pipeline, resolved[name]), f"{option} {name}={raw}")
        for name, raw in settings.items()
    }


def typed_axes(pipeline: Any, axes: Dict[str, List[str]], option: str = "--param") -> Dict[str, List[Any]]:
    """``{name: [raw texts]}`` -> ``{name: [typed values]}`` (one list per swept parameter)."""
    resolved = _resolve(pipeline, list(axes), option)
    typed: Dict[str, List[Any]] = {}
    for name, texts in axes.items():
        spec = _value_spec(pipeline, resolved[name])
        separator = ";" if spec.get("kind") in TUPLE_KINDS or isinstance(spec.get("value"), tuple) else ","
        values = [part.strip() for text in texts for part in text.split(separator) if part.strip()]
        if not values:
            raise ParameterError(f"{option} {name}=: no value to sweep (e.g. {option} {name}=0.5,1,2)")
        typed[name] = [convert(raw, spec, f"{option} {name}={raw}") for raw in values]
    return typed


def check_step_names(pipeline: Any, steps: Dict[str, int]) -> None:
    """Unknown ``--steps`` names fail like the others."""
    _resolve(pipeline, list(steps), "--steps")


def output_selector(raw: Optional[str]) -> Any:
    """``--output`` value: a name, an index (``0``), ``all`` or a comma-separated list."""
    if raw is None:
        return None
    items: List[Any] = [int(item) if item.strip().isdigit() else item.strip() for item in raw.split(",")]
    return items[0] if len(items) == 1 else items
