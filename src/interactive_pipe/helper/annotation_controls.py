"""Controls declared by a filter's own type annotations.

Under ``@interactive``, a typed signature is enough to declare a widget::

    @interactive()
    def adjust(
        img,
        gain: Annotated[float, (0.0, 3.0)] = 1.0,  # float slider
        radius: Annotated[int, (1, 15, 2), "Blur radius"] = 3,  # int slider, step 2, label
        flip: Annotated[bool, "Flip"] = False,  # checkbox
        mode: Literal["dark", "light"] = "dark",  # dropdown
        style: Style = Style.FLAT,  # Enum -> dropdown over the members
        window: Annotated[Tuple[float, float], (0.0, 1.0)] = (0.2, 0.8),  # range slider
        angle: Annotated[float, CircularControl(0.0, [0.0, 360.0])] = 0.0,  # any Control
    ): ...

Only explicit opt-ins make a widget: ``Annotated[...]`` with a range / choices /
``Control`` (or a label on a bool), a ``Literal`` and an ``Enum`` hint. A plain
``gain: float = 1.0`` or ``flip: bool = False`` stays a parameter without widget.
The ``Annotated`` metadata after the type is what the tuple shorthand accepts
after the default (``(min, max[, step])`` or the list of choices, then an
optional label and group); the default comes from the signature.
"""

import enum
import inspect
import logging
import typing
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from interactive_pipe.headless.control import Control, MappedChoiceControl, RangeControl
from interactive_pipe.headless.panel import Panel

try:  # Python 3.9+ (typing); typing_extensions aliases resolve to the same objects
    from typing import Annotated, Literal, get_args, get_origin
except ImportError:  # pragma: no cover - Python < 3.9 is not supported
    Annotated = Literal = None  # type: ignore

_EMPTY = inspect.Parameter.empty
_NUMBER = (int, float)


def _where(func: Callable) -> str:
    try:
        filename = inspect.getsourcefile(func) or func.__code__.co_filename
        return f" ({filename}:{func.__code__.co_firstlineno})"
    except (TypeError, AttributeError):
        return ""


def annotation_error(
    func: Callable, param_name: str, problem: str, fix: str, exc_type: Type[Exception] = ValueError
) -> Exception:
    """Decoration-time error naming the filter, the parameter and the fix."""
    return exc_type(
        f"@interactive filter '{getattr(func, '__qualname__', func)}'{_where(func)}, "
        f"parameter '{param_name}': {problem}. Fix: {fix}"
    )


def resolve_type_hints(func: Callable, localns: Optional[dict] = None) -> Dict[str, Any]:
    """``get_type_hints(include_extras=True)``, tolerant to unresolvable hints.

    ``from __future__ import annotations`` turns every hint into a string;
    ``typing.get_type_hints`` evaluates them all at once and fails on the first
    unknown name. Then each hint is evaluated on its own and the ones that still
    cannot be resolved are skipped (they make no widget), with a warning when the
    hint looks like a control declaration.
    """
    try:
        return typing.get_type_hints(func, localns=localns, include_extras=True)
    except Exception:  # Broad on purpose: NameError, TypeError, SyntaxError... from user hints
        pass
    globalns = getattr(func, "__globals__", {})
    hints = {}
    for name, hint in getattr(func, "__annotations__", {}).items():
        if isinstance(hint, str):
            try:
                hint = eval(hint, globalns, dict(localns or {}))  # noqa: S307 - same as get_type_hints
            except Exception:  # Broad on purpose: arbitrary annotation text
                if any(word in hint for word in ("Annotated", "Literal")):
                    logging.warning(
                        f"@interactive filter '{getattr(func, '__qualname__', func)}': cannot resolve the "
                        f"annotation of '{name}' ({hint!r}), no widget is created for it. Make the names it "
                        "uses importable at module level."
                    )
                continue
        hints[name] = hint
    return hints


def _split_annotated(hint) -> Tuple[Any, tuple]:
    if Annotated is not None and get_origin(hint) is Annotated:
        args = get_args(hint)
        return args[0], tuple(args[1:])
    return hint, ()


def _is_enum_type(hint) -> bool:
    return isinstance(hint, type) and issubclass(hint, enum.Enum)


def _is_literal(hint) -> bool:
    return Literal is not None and get_origin(hint) is Literal


def _choice_map(func: Callable, param_name: str, base) -> Optional[dict]:
    """label -> value for a Literal or Enum hint (None when every value is its own label)."""
    if _is_enum_type(base):
        members = list(base)
        if not members:
            raise annotation_error(func, param_name, f"enum {base.__name__} has no member", "add members")
        return {member.name: member for member in members}
    values = list(get_args(base))
    if not values:
        raise annotation_error(func, param_name, "Literal[] has no choice", "list the choices")
    if all(type(value) is str for value in values):
        return None
    mapping: Dict[str, Any] = {}
    for value in values:
        label = value.name if isinstance(value, enum.Enum) else str(value)
        if label in mapping:
            raise annotation_error(
                func,
                param_name,
                f"two Literal choices are both displayed as {label!r}",
                "use distinct values",
            )
        mapping[label] = value
    return mapping


def _labels(func: Callable, param_name: str, metadata: List[Any]) -> Tuple[Optional[str], Any]:
    """Optional label (control name) and group from the trailing metadata."""
    strings = [item for item in metadata if isinstance(item, (str, Panel))]
    if len(strings) > 2:
        raise annotation_error(
            func,
            param_name,
            f"too many labels {strings!r}",
            "write at most a label then a group, e.g. Annotated[float, (0.0, 1.0), 'Gain', 'Exposure']",
        )
    name = strings[0] if strings else None
    group = strings[1] if len(strings) > 1 else None
    if name is not None and not isinstance(name, str):
        raise annotation_error(func, param_name, f"the label must be a string, got {name!r}", "pass the label first")
    return name, group


def _check_type(func: Callable, param_name: str, base, default):
    """Default checked against (and coerced to) the hinted type."""
    if base is float:
        if isinstance(default, bool) or not isinstance(default, _NUMBER):
            raise annotation_error(
                func,
                param_name,
                f"the default {default!r} is not a float",
                f"use a number as default, e.g. {param_name}: ... = 1.0",
                TypeError,
            )
        return float(default)
    if base is int:
        if isinstance(default, bool) or not isinstance(default, int):
            raise annotation_error(
                func,
                param_name,
                f"the default {default!r} is not an int",
                f"use an int default (e.g. = {int(default) if isinstance(default, float) else 1}) "
                "or annotate the parameter as float",
                TypeError,
            )
        return default
    if base is bool and not isinstance(default, bool):
        raise annotation_error(
            func, param_name, f"the default {default!r} is not a bool", "use True or False as default", TypeError
        )
    if base is str and not isinstance(default, str):
        raise annotation_error(
            func, param_name, f"the default {default!r} is not a string", "use one of the choices as default", TypeError
        )
    return default


def _numeric_range(func: Callable, param_name: str, base, spec) -> Tuple[list, Any]:
    if len(spec) not in (2, 3):
        raise annotation_error(
            func,
            param_name,
            f"{spec!r} is not a range",
            "write (min, max) or (min, max, step); the default goes in the signature",
        )
    low, high = spec[0], spec[1]
    step = spec[2] if len(spec) == 3 else None
    for bound in (low, high):
        if isinstance(bound, bool) or not isinstance(bound, _NUMBER):
            raise annotation_error(
                func, param_name, f"range bound {bound!r} is not a number", "write (min, max) with numbers", TypeError
            )
    if base is int:
        if not (float(low).is_integer() and float(high).is_integer()):
            raise annotation_error(
                func,
                param_name,
                f"the range {spec!r} of an int is not made of ints",
                "use int bounds or annotate float",
            )
        low, high = int(low), int(high)
    elif base is float:
        low, high = float(low), float(high)
    if low > high:
        raise annotation_error(
            func, param_name, f"the range ({low}, {high}) is reversed", f"write ({high}, {low}): (min, max)"
        )
    if step is not None:
        if isinstance(step, bool) or not isinstance(step, _NUMBER) or step <= 0:
            raise annotation_error(func, param_name, f"the step {step!r} is not a positive number", "use a step > 0")
        if high > low and step > high - low:
            raise annotation_error(
                func,
                param_name,
                f"the step {step!r} is larger than the range ({low}, {high})",
                f"use a step <= {high - low}",
            )
        if base is int and not float(step).is_integer():
            raise annotation_error(func, param_name, f"the step {step!r} of an int slider is not an int", "use an int")
        if base is int:
            step = int(step)
    return [low, high], step


def _in_range(func: Callable, param_name: str, default, value_range: list) -> None:
    low, high = value_range
    if not low <= default <= high:
        raise annotation_error(
            func,
            param_name,
            f"the default {default!r} is outside the annotated range ({low}, {high})",
            "change the default or widen the range",
        )


def _from_control(func: Callable, param_name: str, ctrl: Control, default) -> Tuple[Control, Any]:
    """Per-function clone of a Control found in an annotation.

    The annotation object can be shared (a type alias used by several filters)
    and pipelines rename / connect the controls they get: never hand out the
    annotation instance itself.
    """
    name = param_name if (ctrl._auto_named or ctrl.name is None) else ctrl.name
    clone = ctrl._clone_unconnected(name)
    clone._auto_named = ctrl._auto_named
    if default is not _EMPTY and default != clone.value_default:
        try:
            clone = clone._clone_with_default(default, name=name)
        except (TypeError, ValueError) as exc:
            raise annotation_error(
                func,
                param_name,
                f"the signature default {default!r} does not fit the annotated control ({exc})",
                "make the signature default match the control",
                type(exc),
            ) from None
        clone._auto_named = ctrl._auto_named
    return clone, clone.value_default


def control_from_annotation(func: Callable, param_name: str, hint, default) -> Optional[Tuple[Control, Any]]:
    """Control declared by one parameter's annotation and its (signature) default.

    Returns None when the annotation does not opt into a widget.
    """
    if default is None:
        # `mode: Literal["a", "b"] = None` usually means "automatic": no widget.
        # (Python < 3.11 get_type_hints also turns such hints into Optional[...],
        # which is not an opt-in either, so every version behaves the same.)
        candidates = get_args(hint) if get_origin(hint) is typing.Union else (hint,)
        metadata = [item for candidate in candidates for item in _split_annotated(candidate)[1]]
        if any(isinstance(item, (Control, list, tuple, str)) for item in metadata):
            logging.warning(
                f"@interactive filter '{getattr(func, '__qualname__', func)}', parameter '{param_name}': "
                "the default None makes no widget. Give a default value to get one."
            )
        return None
    if get_origin(hint) is typing.Union:
        return None  # Optional[...] / Union[...]: not an opt-in
    base, metadata = _split_annotated(hint)
    controls = [item for item in metadata if isinstance(item, Control)]
    if len(controls) > 1:
        raise annotation_error(func, param_name, "several Control objects in one annotation", "keep only one")
    if controls:
        return _from_control(func, param_name, controls[0], default)

    specs = [item for item in metadata if isinstance(item, (list, tuple))]
    if len(specs) > 1:
        raise annotation_error(
            func, param_name, f"several ranges {specs!r} in one annotation", "keep one (min, max[, step])"
        )
    spec = specs[0] if specs else None
    name, group = _labels(func, param_name, list(metadata))

    if _is_literal(base) or _is_enum_type(base):
        if spec is not None:
            raise annotation_error(
                func,
                param_name,
                f"a {'Literal' if _is_literal(base) else 'Enum'} already lists the choices, {spec!r} is not used",
                "remove the extra choices / range from Annotated",
            )
        mapping = _choice_map(func, param_name, base)
        choices = list(get_args(base)) if mapping is None else list(mapping.values())
        if not any(default is choice or (type(default) is type(choice) and default == choice) for choice in choices):
            raise annotation_error(
                func,
                param_name,
                f"the default {default!r} is not one of the choices {choices!r}",
                "use one of the choices as default",
            )
        if mapping is None:
            control = Control(default, list(choices), name=name, group=group)
        else:
            control = MappedChoiceControl(mapping, default, name=name, group=group)
        return control, default

    if not metadata:
        return None  # a plain hint (float, bool, ...) never makes a widget

    if base is bool:
        if spec is not None:
            raise annotation_error(
                func,
                param_name,
                f"a checkbox takes no range, got {spec!r}",
                f"write Annotated[bool, 'label'] (e.g. {param_name}: Annotated[bool, 'Flip'] = False)",
            )
        if name is None:
            return None  # foreign metadata only
        default = _check_type(func, param_name, bool, default)
        return Control(default, name=name, group=group), default

    if spec is None:
        if name is not None:
            logging.warning(
                f"@interactive filter '{getattr(func, '__qualname__', func)}', parameter '{param_name}': "
                f"Annotated label {name!r} without a range or choices makes no widget. "
                f"Write Annotated[float, (min, max), {name!r}] for a slider or a list of choices for a dropdown."
            )
        return None

    tuple_like = get_origin(base) is tuple or base is tuple
    if tuple_like or (isinstance(default, (tuple, list)) and len(default) == 2):
        value_range, step = _numeric_range(func, param_name, None, spec)
        try:
            control = RangeControl(tuple(default), value_range, step=step, name=name, group=group)
        except (TypeError, ValueError) as exc:
            raise annotation_error(
                func, param_name, f"invalid range default {default!r} ({exc})", "use a (lo, hi) pair inside the range"
            ) from None
        return control, tuple(default)

    if all(isinstance(item, str) for item in spec):
        # dropdown of string choices: Annotated[str, ["dark", "light"]]
        if not spec:
            raise annotation_error(func, param_name, "the list of choices is empty", "list at least one choice")
        if base not in (str, Any) and not isinstance(default, str):
            raise annotation_error(
                func, param_name, f"string choices {list(spec)!r} for a {base!r} hint", "annotate the parameter as str"
            )
        default = _check_type(func, param_name, str, default)
        if default not in spec:
            raise annotation_error(
                func,
                param_name,
                f"the default {default!r} is not one of the choices {list(spec)!r}",
                "use one of the choices as default",
            )
        return Control(default, list(spec), name=name, group=group), default

    numeric_base = base if base in (int, float) else None
    value_range, step = _numeric_range(func, param_name, numeric_base, spec)
    if numeric_base is not None:
        default = _check_type(func, param_name, numeric_base, default)
    elif isinstance(default, bool) or not isinstance(default, _NUMBER):
        raise annotation_error(
            func, param_name, f"the default {default!r} is not a number", "use a number as default", TypeError
        )
    _in_range(func, param_name, default, value_range)
    try:
        control = Control(default, value_range, name=name, step=step, group=group)
    except (TypeError, ValueError) as exc:
        raise annotation_error(func, param_name, str(exc), "fix the annotation", type(exc)) from None
    return control, default


def controls_from_annotations(
    func: Callable, skip: Optional[set] = None, localns: Optional[dict] = None
) -> Dict[str, Control]:
    """Controls declared by annotations.

    ``skip``: parameters declared in the decorator (the decorator wins, their
    annotation is not read). Only parameters with a default are considered: a
    parameter without default is a pipeline input, whatever its hint
    (``mode: Mode`` may be produced by an upstream filter). A default that is
    itself a declaration (``Control(...)`` or a tuple shorthand) wins over the
    annotation, like the decorator does.
    """
    skip = skip or set()
    hints = resolve_type_hints(func, localns)
    if not hints:
        return {}
    controls: Dict[str, Control] = {}
    for param in inspect.signature(func).parameters.values():
        if param.name in skip or param.name not in hints:
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD, param.POSITIONAL_ONLY):
            continue
        if param.default is _EMPTY or isinstance(param.default, Control):
            continue
        hint = hints[param.name]
        base, metadata = _split_annotated(hint)
        if (
            isinstance(param.default, (list, tuple))
            and not _is_tuple_hint(base)
            and not any(isinstance(item, Control) for item in metadata)
        ):
            continue  # signature tuple shorthand: (default, [min, max])
        found = control_from_annotation(func, param.name, hint, param.default)
        if found is None:
            continue
        control, _default = found
        if control.name is None or control._auto_named:
            control.name = param.name
            control._auto_named = True
        controls[param.name] = control
    return controls


def _is_tuple_hint(base) -> bool:
    return base is tuple or get_origin(base) is tuple
