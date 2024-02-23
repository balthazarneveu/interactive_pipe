from interactive_pipe.headless.control import Control
from interactive_pipe.helper.control_abbreviation import control_from_tuple
from typing import Callable, Union
from interactive_pipe.core.graph import analyze_apply_fn_signature
from interactive_pipe.helper import _private


def __create_control_from_keyword_argument(
    param_name: str,
    unknown_keyword_arg: Union[Control, list, tuple]
) -> Union[None, Control]:
    """Create a Control from a given keyword argument named  param_name with value unknown_keyword_arg

    - If unknown_keyword_arg is already a Control, nothing to do.
    - If unknown_keyword_arg is a tuple or a list or something else, 
    guess the Slider declaration automatically (see `control_from_tuple`)

    You cannot have several controls which have the same attribute .name
    See https://github.com/balthazarneveu/interactive_pipe/issues/35 for more details
    """
    chosen_control = None
    if isinstance(unknown_keyword_arg, Control):  # This includes KeyboardControl aswell!!
        if unknown_keyword_arg.name is None or unknown_keyword_arg._auto_named:
            unknown_keyword_arg.name = param_name
        chosen_control = unknown_keyword_arg
    else:
        if isinstance(unknown_keyword_arg, list) or isinstance(unknown_keyword_arg, tuple):
            try:
                chosen_control = control_from_tuple(
                    unknown_keyword_arg, param_name=param_name)
            except Exception as exc_1:
                try:
                    chosen_control = control_from_tuple(
                        (unknown_keyword_arg,), param_name=param_name)
                except Exception as exc:
                    raise Exception(exc)
            # NOTE: for keyword args, setting a boolean will not trigger a tickmark (although it is possible)
            # Use (True) instead of True if you want to make a tickbox
    if chosen_control is not None:
        assert chosen_control.name not in _private.registered_controls_names, f"{chosen_control.name} already attributed - {_private.registered_controls_names}"
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
        chosen_control = __create_control_from_keyword_argument(
            param_name, unknown_keyword_arg)
        if chosen_control is not None:
            controls[param_name] = chosen_control

    # 2. Analyzing decorator keyword args
    # @interactive(param_2=Control(...))
    for param_name, unknown_keyword_arg in decorator_controls.items():
        assert param_name in keyword_names, f"typo: control {param_name} passed through the decorator does not match any of the function keyword args {keyword_names}"
        chosen_control = __create_control_from_keyword_argument(
            param_name, unknown_keyword_arg)
        if chosen_control is not None:
            controls[param_name] = chosen_control

    for param_name, unknown_control in controls.items():
        Control.register(func.__name__, param_name, controls[param_name])
    return controls
