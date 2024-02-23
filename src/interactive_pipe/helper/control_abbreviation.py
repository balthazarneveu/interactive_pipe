from interactive_pipe.headless.control import Control
from interactive_pipe.headless.keyboard import KeyboardControl
from typing import Union, Tuple
import logging


def analyze_expected_keyboard_argument(arg) -> Tuple[bool, Union[str, None], Union[str, None], bool]:
    """
    keydown
    [keydown]
    (keydown)
    [keydown, True]
    (keydown, True)
    (keydown, keyup, True)
    [keydown, keyup, True]
    (None   , keyup)
    [None   , keyup]
    (None   , keyup, True)
    [None   , keyup, True]
    """
    keyboard_slider_flag, keydown, keyup, modulo = True, None, None, False
    if arg is None:
        # supported None strange definition...
        logging.warning(
            "Setting a Control with a None argument where it expects some key definition for KeyboardControl. Prefer simply ignoring this argument")
        keyboard_slider_flag = False
        pass
    elif isinstance(arg, str):
        # single key - if not setting the modulo, you cannot increase the value
        keydown = KeyboardControl.sanity_check_key(arg)
    elif isinstance(arg, list) or isinstance(arg, tuple):
        if len(arg) == 0:
            logging.warning(
                "Setting a Control with an empty list where it expects some key definition for KeyboardControl. Prefer simply ignoring this argument")
            keyboard_slider_flag = False
        else:
            keydown = None if arg[0] is None else KeyboardControl.sanity_check_key(
                arg[0])
            if len(arg) == 2:
                if isinstance(arg[1], bool):
                    modulo = arg[1]
                else:
                    keyup = None if arg[1] is None else KeyboardControl.sanity_check_key(
                        arg[1])
            elif len(arg) == 3:
                keyup = None if arg[1] is None else KeyboardControl.sanity_check_key(
                    arg[1])
                assert isinstance(
                    arg[2], bool), f"modulo shall be a boolean, found {arg[2]}"
                modulo = arg[2]
            else:
                raise ValueError(
                    f"Too much elements in the keyboard provided list {arg} , stick to 3 maximum [keydown, keyup, modulo]")
    else:
        raise TypeError(f"{arg} is not supported for keyboard")
    return keyboard_slider_flag, keydown, keyup, modulo


def default_value_check(val):
    if isinstance(val, bool) or isinstance(val, int) or isinstance(val, float) or isinstance(val, str):
        return True
    elif isinstance(val, tuple) or isinstance(val, list):
        return False
    else:
        raise TypeError(f"{type(val)} is not supported")


def control_from_tuple(short_params: Tuple, param_name: str = None) -> Union[Control,  KeyboardControl]:
    '''Define a Control or Keyboard control from a short declaration

    - Classic mode:
        - `(default_value, value_range: [min, max, step], optional_name, optional_keyboard: [keydown, up, modulo])`
        - `(default_string, value_choices: [A, B, C...], optional_name, optional_keyboard: [keydown, up, modulo])`
        - `(True/False, optional_name, optional_key)`
    - Ultra short mode:
        - `[min, max, step, optional_default_value)], optional_name, optional_keyboard: [keydown, up, modulo]`
        - `[default_A, B, C, D...], optional_name, optional_keyboard:[keydown, up, modulo]`


    Ultra short examples
    ---------------------
    - [-10, 10] -> slider from -10 to 10, default is 0 (middle cursor)
    - [-10.5, 18., None, 15.] -> slider from -10.5 to 18., default is 15., no step provided
    - [-5, 5], _name, ["-", "+", True] -> use keyboard -/+ to decrease the value. True indicates a wrap around(modulo). default=0 (in the middle)
    - ["A", "B", "C"] -> dialog, default is A
    - (True, _name) -> checkbox checked by default
    - (False, ) -> checkbox, unchecked by default



    Regular examples
    ----------------
    (0., [-1, 1.], name),  (0., [-1, 1., 1], name)...
    (True, name)

    (0., [-1, 1.], name, [keydown, keyup]),  (0., [-1, 1., 1], name, [keydown, keyup, modulo])...
    (True, name, key)
    '''

    if isinstance(short_params, bool):
        return Control(short_params, name=param_name)
    assert isinstance(short_params, tuple) or isinstance(
        short_params, list), f"issue with {param_name}, {short_params}"
    value_default = short_params[0]
    first_value_is_default_val = default_value_check(value_default)
    name = None
    step = None
    keyboard_slider_flag = False
    if isinstance(value_default, bool):
        # BOOLEAN
        value_range = None
        if len(short_params) >= 2:
            name = short_params[1]
            if name is not None:
                assert isinstance(
                    name, str), f"{name} name shall be a string or None. you do not need to provide a value range for a boolean slider."
            assert len(short_params) <= 3
            if len(short_params) == 3:
                keyboard_slider_flag, keydown, keyup, _modulo = analyze_expected_keyboard_argument(
                    short_params[2])
                modulo = True
    else:
        if first_value_is_default_val:
            # INT/FLOAT/STR
            start = 1
            assert len(
                short_params) >= 2, f"providing a value range is mandatory like (min, max) or (min, max, step)"
            value_range = short_params[start]
            assert isinstance(value_range, list) or isinstance(
                value_range, tuple), f"value range should be a tuple or a list, provided {value_range}"
            if (isinstance(value_default, float) or isinstance(value_default, int)) and len(value_range) >= 3:
                step = value_range[2]
                value_range = value_range[:2]
        else:
            # ["cat", "dog", "tree"] -> default value = "cat"
            # [-10, 10, 1] -> default val = average(-10, 10), step=1
            # [-10, 10] -> default val = average(-10, 10)
            # [-10, 10, 1/None, 5], default val = 5, step=None
            value_default = None
            start = 0
            special_list = short_params[0]
            assert len(
                special_list) > 0, "cannot provide an empty list or tuple"

            if all(isinstance(item, str) for item in special_list):
                # ["cat", "dog", "tree"] -> default value = "cat"
                value_default = special_list[0]
                value_range = special_list
            elif isinstance(special_list[0], int) or isinstance(special_list[0], float):
                assert len(
                    special_list) >= 2, "please provide [min, max], [min, max, step], [min, max, None, default]"
                assert isinstance(special_list[1], int) or isinstance(
                    special_list[1], float), f"min={special_list[0]} max={special_list[1]} - max parameter should be numerical too"
                value_range = special_list[:2]

                if len(special_list) >= 3:
                    # [-10, 10, 1] -> default val = average(-10, 10), step=1
                    step = special_list[2]
                    if step is not None:
                        assert isinstance(step, int) or isinstance(
                            step, float), f"{step} has to be numerical"
                    if len(special_list) == 4:
                        # [-10, 10, 1] -> default val = average(-10, 10), step=1
                        value_default = special_list[3]
                if value_default is None:
                    if isinstance(value_range[0], int) and isinstance(value_range[1], int):
                        value_default = (value_range[0] + value_range[1])//2
                    else:
                        value_default = (value_range[0] + value_range[1])/2.
            else:
                raise ValueError(f"wrong abbreviation {special_list}")

        if len(short_params) >= start+2:
            name = short_params[start+1]
        assert len(short_params) <= start+3
        if len(short_params) == start+3:
            keyboard_slider_flag, keydown, keyup, modulo = analyze_expected_keyboard_argument(
                short_params[start+2])

    if name is None:
        name = param_name
    if keyboard_slider_flag:
        return KeyboardControl(value_default, value_range=value_range, name=name, step=step, keydown=keydown, keyup=keyup, modulo=modulo)
    return Control(value_default, value_range=value_range, name=name, step=step)
