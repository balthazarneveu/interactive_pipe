import logging
from typing import Callable, Union

from interactive_pipe.core.graph import analyze_apply_fn_signature
from interactive_pipe.headless.control import Control
from interactive_pipe.helper import _private
from interactive_pipe.helper.control_abbreviation import control_from_tuple


def __create_control_from_keyword_argument(
    param_name: str, unknown_keyword_arg: Union[Control, list, tuple]
) -> Union[None, Control]:
    """Create a Control from a given keyword argument named  param_name with value unknown_keyword_arg

    - If unknown_keyword_arg is already a Control, nothing to do.
    - If unknown_keyword_arg is a tuple or a list or something else,
    guess the Slider declaration automatically (see `control_from_tuple`)

    You cannot have several controls which have the same attribute .name
    See https://github.com/balthazarneveu/interactive_pipe/issues/35 for more details
    """
    chosen_control = None
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
            except Exception as first_exc:
                try:
                    chosen_control = control_from_tuple((unknown_keyword_arg,), param_name=param_name)
                except Exception as exc:
                    logging.debug(f"could not build control from bare value {param_name}: {first_exc}")
                    raise ValueError(
                        f"Cannot create a control from {param_name}={unknown_keyword_arg!r}: {exc}"
                    ) from exc
            # NOTE: for keyword args, setting a boolean will not trigger a tickmark (although it is possible)
            # Use (True) instead of True if you want to make a tickbox
    if chosen_control is not None:
        if chosen_control.name in _private.registered_controls_names:
            raise ValueError(f"{chosen_control.name} already attributed - {_private.registered_controls_names}")
        _private.registered_controls_names.append(chosen_control.name)
    return chosen_control


def get_controls_from_decorated_function_declaration(func: Callable, decorator_controls: dict):
    controls = {}
    keyword_args = analyze_apply_fn_signature(func)[1]
    keyword_names = list(keyword_args.keys())

    # Analyze at 2 levels (function keyword args & decorator keyword args)  then register controls when necessary.
    # -------------------------------------------
    # @interactive(param_2=Control(...), )
    # def func(img1, img2, param_1=Control(...)):
    # -------------------------------------------

    # 1. Analyzing function keyword args
    # def func(img1, img2, param_1=Control(...))

    for param_name, unknown_keyword_arg in keyword_args.items():
        chosen_control = __create_control_from_keyword_argument(param_name, unknown_keyword_arg)
        if chosen_control is not None:
            controls[param_name] = chosen_control

    # 2. Analyzing decorator keyword args
    # @interactive(param_2=Control(...))
    for param_name, unknown_keyword_arg in decorator_controls.items():
        if param_name not in keyword_names:
            raise ValueError(
                f"typo: control {param_name} passed through the decorator "
                f"does not match any of the function keyword args {keyword_names}"
            )
        chosen_control = __create_control_from_keyword_argument(param_name, unknown_keyword_arg)
        if chosen_control is not None:
            controls[param_name] = chosen_control

    for param_name, control in controls.items():
        Control.register(func.__name__, param_name, control)
    return controls
