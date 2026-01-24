from interactive_pipe.headless.control import (
    Control,
    RangeSliderHandle,
    RangeSlider,
    RangeSliderControlWrapper,
)
from interactive_pipe.helper.control_abbreviation import control_from_tuple
from typing import Callable, Union, Dict, Optional
from interactive_pipe.core.graph import analyze_apply_fn_signature
from interactive_pipe.helper import _private


def __create_control_from_keyword_argument(
    param_name: str, unknown_keyword_arg: Union[Control, list, tuple, RangeSliderHandle]
) -> Union[None, Control, RangeSliderHandle]:
    """Create a Control from a given keyword argument named  param_name with value unknown_keyword_arg

    - If unknown_keyword_arg is already a Control, nothing to do.
    - If unknown_keyword_arg is a RangeSliderHandle, return it as-is (will be processed later)
    - If unknown_keyword_arg is a tuple or a list or something else,
    guess the Slider declaration automatically (see `control_from_tuple`)

    You cannot have several controls which have the same attribute .name
    See https://github.com/balthazarneveu/interactive_pipe/issues/35 for more details
    """
    chosen_control = None
    if isinstance(unknown_keyword_arg, RangeSliderHandle):
        # Return RangeSliderHandle as-is - will be processed in get_controls_from_decorated_function_declaration
        return unknown_keyword_arg
    elif isinstance(
        unknown_keyword_arg, Control
    ):  # This includes KeyboardControl aswell!!
        if unknown_keyword_arg.name is None or unknown_keyword_arg._auto_named:
            unknown_keyword_arg.name = param_name
        chosen_control = unknown_keyword_arg
    else:
        if isinstance(unknown_keyword_arg, list) or isinstance(
            unknown_keyword_arg, tuple
        ):
            try:
                chosen_control = control_from_tuple(
                    unknown_keyword_arg, param_name=param_name
                )
            except Exception as _exc_1:
                try:
                    chosen_control = control_from_tuple(
                        (unknown_keyword_arg,), param_name=param_name
                    )
                except Exception as exc:
                    print(_exc_1)
                    raise Exception(exc)
            # NOTE: for keyword args, setting a boolean will not trigger a tickmark (although it is possible)
            # Use (True) instead of True if you want to make a tickbox
    if chosen_control is not None:
        assert (
            chosen_control.name not in _private.registered_controls_names
        ), f"{chosen_control.name} already attributed - {_private.registered_controls_names}"
        _private.registered_controls_names.append(chosen_control.name)
    return chosen_control


def get_controls_from_decorated_function_declaration(
    func: Callable, decorator_controls: dict
):
    controls = {}
    keyword_args = analyze_apply_fn_signature(func)[1]
    keyword_names = list(keyword_args.keys())

    # Track RangeSliderHandle objects to group them later
    range_slider_handles: Dict[RangeSlider, Dict[str, str]] = {}  # RangeSlider -> {side: param_name}

    # Analyze at 2 levels (function keyword args & decorator keyword args)  then register controls when necessary.
    # -------------------------------------------
    # @interactive(param_2=Control(...), )
    # def func(img1, img2, param_1=Control(...)):
    # -------------------------------------------

    # 1. Analyzing function keyword args
    # def func(img1, img2, param_1=Control(...))

    for param_name, unknown_keyword_arg in keyword_args.items():
        chosen_control = __create_control_from_keyword_argument(
            param_name, unknown_keyword_arg
        )
        if isinstance(chosen_control, RangeSliderHandle):
            # Store handle for later processing
            parent = chosen_control.parent
            if parent not in range_slider_handles:
                range_slider_handles[parent] = {}
            range_slider_handles[parent][chosen_control.side] = param_name
        elif chosen_control is not None:
            controls[param_name] = chosen_control

    # 2. Analyzing decorator keyword args
    # @interactive(param_2=Control(...))
    for param_name, unknown_keyword_arg in decorator_controls.items():
        assert param_name in keyword_names, (
            f"typo: control {param_name} passed through the decorator "
            f"does not match any of the function keyword args {keyword_names}"
        )
        chosen_control = __create_control_from_keyword_argument(
            param_name, unknown_keyword_arg
        )
        if isinstance(chosen_control, RangeSliderHandle):
            # Store handle for later processing
            parent = chosen_control.parent
            if parent not in range_slider_handles:
                range_slider_handles[parent] = {}
            range_slider_handles[parent][chosen_control.side] = param_name
        elif chosen_control is not None:
            controls[param_name] = chosen_control

    # Process RangeSlider handles - create wrapper controls
    for range_slider, handle_mapping in range_slider_handles.items():
        if "left" not in handle_mapping or "right" not in handle_mapping:
            raise ValueError(
                f"RangeSlider {range_slider.name} must have both .left and .right handles bound to parameters. "
                f"Found: {handle_mapping}"
            )
        left_param = handle_mapping["left"]
        right_param = handle_mapping["right"]
        
        # Create wrapper control
        wrapper = RangeSliderControlWrapper(
            range_slider=range_slider,
            left_param_name=left_param,
            right_param_name=right_param,
        )
        
        # Create individual parameter controls for function signature defaults
        # These need to be in controls dict so the decorator can resolve their values
        # They will be updated by the wrapper when the slider changes
        # Mark them so they're not added to control_list (only wrapper is shown in GUI)
        left_control = Control(
            value_default=range_slider.default[0],
            value_range=range_slider.value_range,
            name=left_param,
        )
        left_control._type = range_slider._type
        left_control._is_range_slider_param = True  # Mark as range slider parameter
        left_control._range_slider_wrapper = wrapper  # Store reference to wrapper
        controls[left_param] = left_control
        
        right_control = Control(
            value_default=range_slider.default[1],
            value_range=range_slider.value_range,
            name=right_param,
        )
        right_control._type = range_slider._type
        right_control._is_range_slider_param = True  # Mark as range slider parameter
        right_control._range_slider_wrapper = wrapper  # Store reference to wrapper
        controls[right_param] = right_control
        
        # Store references in the wrapper for later value updates
        wrapper._left_control = left_control
        wrapper._right_control = right_control
        
        # Register the wrapper separately so Control.get_controls() can find it
        # But DON'T add it to controls dict - it's not a function parameter
        # The wrapper name is used as a key to find it in the registry
        Control.register(func.__name__, wrapper.name, wrapper)

    for param_name, unknown_control in controls.items():
        Control.register(func.__name__, param_name, controls[param_name])
    return controls
