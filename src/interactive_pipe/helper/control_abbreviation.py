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
        logging.warning("Setting a Control with a None argument where it expects some key definition for KeyboardControl. Prefer simply ignoring this argument")
        keyboard_slider_flag = False
        pass
    elif isinstance(arg, str):
        # single key - if not setting the modulo, you cannot increase the value
        keydown = KeyboardControl.sanity_check_key(arg)
    elif isinstance(arg, list) or isinstance(arg, tuple):
        if len(arg) == 0:
            logging.warning("Setting a Control with an empty list where it expects some key definition for KeyboardControl. Prefer simply ignoring this argument")
            keyboard_slider_flag = False
        else:
            keydown = KeyboardControl.sanity_check_key(arg[0])
            if len(arg) == 2:
                if isinstance(arg[1], bool):
                    modulo = arg[1]
                else:
                    keyup = KeyboardControl.sanity_check_key(arg[1])
            elif len(arg) == 3:
                keyup = KeyboardControl.sanity_check_key(arg[1])
                assert isinstance(arg[2], bool), f"modulo shall be a boolean, found {arg[2]}"
                modulo = arg[2]
            else:
                raise ValueError(f"Too much elements in the keyboard provided list {arg} , stick to 3 maximum [keydown, keyup, modulo]")
    else:
        raise ValueError(f"{arg} is not supported")
    return keyboard_slider_flag, keydown, keyup, modulo


def control_from_tuple(short_params: Tuple, param_name :str =None) -> Union[Control,  KeyboardControl]:
    '''
    Define a Control or Keyboard control from a short declaration
    (0., [-1, 1.], name),  (0., [-1, 1., 1], name)...
    (True, name)

    (0., [-1, 1.], name, [keydown, keyup]),  (0., [-1, 1., 1], name, [keydown, keyup, modulo])...
    (True, name, key)
    '''

    if isinstance(short_params, bool):
        return Control(short_params, name=param_name)
    assert isinstance(short_params, tuple) or isinstance(short_params, list), f"issue with {param_name}, {short_params}"
    value_default = short_params[0]
    name = None
    step = None
    keyboard_slider_flag = False
    # BOOLEAN
    if isinstance(value_default, bool):
        value_range = None
        if len(short_params) >= 2:
            name = short_params[1]
            if name is not None:
                assert isinstance(name, str), f"{name} name shall be a string or None. you do not need to provide a value range for a boolean slider."
            assert len(short_params)<=3
            if len(short_params) == 3:
                keyboard_slider_flag, keydown, keyup, _modulo = analyze_expected_keyboard_argument(short_params[2])
                modulo = True
    else:
        # Int, Float, Str
        assert len(short_params) >= 2, f"providing a value range is mandatory like (min, max) or (min, max, step)"
        value_range = short_params[1]
        assert isinstance(value_range, list) or isinstance(value_range, tuple)
        if (isinstance(value_default, float) or isinstance(value_default, int)) and len(value_range)>=3:
            step = value_range[2]
            value_range = value_range[:2]
        if len(short_params) >= 3:
            name = short_params[2]
        assert len(short_params)<=4
        if len(short_params) == 4:
            keyboard_slider_flag, keydown, keyup, modulo = analyze_expected_keyboard_argument(short_params[3])
        
    if name is None:
        name=param_name
    if keyboard_slider_flag:
        return KeyboardControl(value_default, value_range=value_range, name=name, step=step, keydown=keydown, keyup=keyup, modulo=modulo)
    return Control(value_default, value_range=value_range, name=name, step=step)
