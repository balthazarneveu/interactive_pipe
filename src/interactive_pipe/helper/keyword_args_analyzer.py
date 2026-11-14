import difflib
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, Tuple, Union

from interactive_pipe.core.graph import analyze_apply_fn_signature
from interactive_pipe.headless.control import Control
from interactive_pipe.helper.annotation_controls import annotation_error, controls_from_annotations
from interactive_pipe.helper.control_abbreviation import control_from_tuple


def _scalar_shorthand_error(param_name: str, value) -> ValueError:
    if isinstance(value, str):
        example = f"{param_name}=({value!r}, [{value!r}, 'other choice'])"
        need = "a list of choices"
    else:
        low, high = (0, 2 * value) if value > 0 else (2 * value, 0) if value < 0 else (0, 1)
        example = f"{param_name}=({value!r}, [{low!r}, {high!r}])"
        need = "a range"
    return ValueError(
        f"@interactive({param_name}={value!r}): a bare value cannot make a widget, {need} is needed. "
        f"Write {example} (or {param_name}=Control(...)) for a widget, "
        f"or set the default in the function signature (def f(..., {param_name}={value!r})) if no widget is wanted."
    )


def __create_control_from_keyword_argument(
    param_name: str,
    unknown_keyword_arg: Union[Control, list, tuple],
    seen_control_names: set,
    from_decorator: bool = False,
) -> Union[None, Control]:
    """Create a Control from a given keyword argument named  param_name with value unknown_keyword_arg

    - If unknown_keyword_arg is already a Control, nothing to do.
    - If unknown_keyword_arg is a tuple or a list or something else,
    guess the Slider declaration automatically (see `control_from_tuple`)

    Control names must be unique within one decorated function
    (`seen_control_names` is scoped per function, so re-decorating in a
    notebook or sharing parameter names across filters is fine).
    See https://github.com/balthazarneveu/interactive_pipe/issues/35 for more details

    Decorator keyword arguments (`from_decorator=True`) always declare a
    widget: a bare bool is a checkbox (`@interactive(flip=True)`), a bare
    number or string raises (a range / list of choices is needed). In the
    function signature a bare value stays a plain default without a widget.
    """
    chosen_control = None
    if from_decorator and isinstance(unknown_keyword_arg, bool):
        unknown_keyword_arg = (unknown_keyword_arg,)
    elif from_decorator and isinstance(unknown_keyword_arg, (int, float, str)):
        raise _scalar_shorthand_error(param_name, unknown_keyword_arg)
    if isinstance(unknown_keyword_arg, Control):  # This includes KeyboardControl as well!!
        if unknown_keyword_arg.name is None or unknown_keyword_arg._auto_named:
            unknown_keyword_arg.name = param_name
        chosen_control = unknown_keyword_arg
    else:
        if isinstance(unknown_keyword_arg, (list, tuple)):
            try:
                # Convert list to tuple for type checking
                tuple_arg = tuple(unknown_keyword_arg) if isinstance(unknown_keyword_arg, list) else unknown_keyword_arg
                chosen_control = control_from_tuple(tuple_arg, param_name=param_name)
            except (TypeError, ValueError, IndexError) as first_exc:
                try:
                    chosen_control = control_from_tuple((unknown_keyword_arg,), param_name=param_name)
                except (TypeError, ValueError, IndexError) as exc:
                    logging.debug(f"could not build control from bare value {param_name}: {first_exc}")
                    # report the error of the form the user wrote: a tuple is the
                    # (default, range, ...) form, a list the ultra-short [min, max] one
                    reported = first_exc if isinstance(unknown_keyword_arg, tuple) else exc
                    raise ValueError(
                        f"Cannot create a control from {param_name}={unknown_keyword_arg!r}: {reported}"
                    ) from reported
            # NOTE: in the function signature, a bare boolean default does not make a checkbox
            # (use (True,) there); in the decorator, a bare boolean does
    if chosen_control is not None:
        if chosen_control.name in seen_control_names:
            raise ValueError(f"{chosen_control.name} already attributed - {sorted(seen_control_names)}")
        seen_control_names.add(chosen_control.name)
    return chosen_control


@contextmanager
def _naming(func: Callable, param_name: str):
    """Prefix control declaration errors with the filter and the parameter they concern."""
    try:
        yield
    except (TypeError, ValueError) as exc:
        message = str(exc)
        if message.startswith("@interactive"):
            raise
        raise type(exc)(
            f"@interactive filter '{getattr(func, '__qualname__', func)}', parameter '{param_name}': {message}"
        ) from exc


def analyze_filter_controls(
    func: Callable, decorator_controls: dict, localns: Optional[dict] = None
) -> Tuple[Dict[str, Control], Dict[str, Any]]:
    """Controls of a decorated filter, and the defaults implied by its annotations.

    Precedence: decorator keyword argument > annotation > signature default
    (``Control(...)`` or tuple shorthand used as a default). The second value maps
    annotation-declared parameters without a signature default to the default
    they get (see ``annotation_controls.signature_with_defaults``).
    """
    controls: Dict[str, Control] = {}
    seen_control_names: set = set()
    # re-decorating (notebook cell re-run, edited declaration) starts from a
    # clean slate: controls removed from the declaration must not linger
    Control._registry.pop(Control.registry_key(func), None)
    annotated_controls, filled_defaults = controls_from_annotations(func, skip=set(decorator_controls), localns=localns)
    keyword_args = analyze_apply_fn_signature(func)[1]
    keyword_names = list(keyword_args.keys()) + [name for name in filled_defaults if name not in keyword_args]

    # Analyze at 3 levels (function keyword args, annotations & decorator keyword args)
    # then register controls when necessary.
    # -------------------------------------------
    # @interactive(param_2=Control(...), )
    # def func(img1, img2, param_1=Control(...), param_3: Annotated[float, (0., 1.)] = 0.5):
    # -------------------------------------------

    # 1. Analyzing function keyword args
    # def func(img1, img2, param_1=Control(...))
    for param_name, unknown_keyword_arg in keyword_args.items():
        if param_name in decorator_controls or param_name in annotated_controls:
            # The decorator (or annotation) wins: the signature default is then a
            # plain value (e.g. ``window=(0.2, 0.8)`` next to
            # ``window=RangeControl(...)``), not a tuple shorthand to turn into a
            # second control.
            continue
        with _naming(func, param_name):
            chosen_control = __create_control_from_keyword_argument(param_name, unknown_keyword_arg, seen_control_names)
        if chosen_control is not None:
            controls[param_name] = chosen_control

    # 2. Annotations: def func(img, gain: Annotated[float, (0.0, 3.0)] = 1.0)
    for param_name, chosen_control in annotated_controls.items():
        if chosen_control.name in seen_control_names:
            raise annotation_error(
                func,
                param_name,
                f"the label {chosen_control.name!r} is already used by another control of this filter",
                "use distinct labels",
            )
        seen_control_names.add(chosen_control.name)
        controls[param_name] = chosen_control

    # 3. Analyzing decorator keyword args
    # @interactive(param_2=Control(...))
    for param_name, unknown_keyword_arg in decorator_controls.items():
        if param_name not in keyword_names:
            close = difflib.get_close_matches(param_name, keyword_names, n=1)
            raise ValueError(
                f"typo: control {param_name} passed through the decorator "
                f"does not match any of the function keyword args {keyword_names} "
                f"(@interactive filter '{getattr(func, '__qualname__', func)}')"
                + (f". Did you mean '{close[0]}'?" if close else "")
            )
        with _naming(func, param_name):
            chosen_control = __create_control_from_keyword_argument(
                param_name, unknown_keyword_arg, seen_control_names, from_decorator=True
            )
        if chosen_control is not None:
            controls[param_name] = chosen_control

    for param_name, control in controls.items():
        Control.register(func, param_name, control)
    return controls, filled_defaults


def get_controls_from_decorated_function_declaration(func: Callable, decorator_controls: dict):
    return analyze_filter_controls(func, decorator_controls)[0]
