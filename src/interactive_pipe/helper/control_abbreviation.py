from typing import List, Optional, Tuple, Union

from interactive_pipe.headless.control import Control
from interactive_pipe.headless.keyboard import KeyboardControl


def _group_error(group) -> str:
    """Message for a group that is neither a string nor a Panel; a list of key
    names is the keyboard form removed in 0.9.0."""
    message = f"{group} group shall be a string or Panel"
    if isinstance(group, (list, tuple)) and group and all(isinstance(key, str) for key in group):
        message += (
            ". Keyboard keys in a control tuple were removed in 0.9.0: use "
            "KeyboardControl(default, [min, max], name=..., keydown=..., keyup=...) instead"
        )
    return message


def default_value_check(val):
    if isinstance(val, (bool, int, float, str)):
        return True
    elif isinstance(val, (tuple, list)):
        return False
    else:
        raise TypeError(f"{type(val)} is not supported")


def control_from_tuple(short_params: Tuple, param_name: Optional[str] = None) -> Union[Control, KeyboardControl]:
    """Define a Control from a short declaration

    - Classic mode:
        - `(default_value, value_range: [min, max, step], optional_name, optional_group)`
        - `(default_value, [min, max, "log"], ...)`: a log slider (``"log"`` in the step slot)
        - `(default_string, value_choices: [A, B, C...], optional_name, optional_group)`
        - `(True/False, optional_name, optional_group)`
    - Ultra short mode:
        - `[min, max, step, optional_default_value], optional_name, optional_group`
        - `[default_A, B, C, D...], optional_name, optional_group`


    Ultra short examples
    ---------------------
    - [-10, 10] -> slider from -10 to 10, default is 0 (middle cursor)
    - [-10.5, 18., None, 15.] -> slider from -10.5 to 18., default is 15., no step provided
    - ["A", "B", "C"] -> dialog, default is A
    - (True, _name) -> checkbox checked by default
    - (False, ) -> checkbox, unchecked by default


    Regular examples
    ----------------
    (0., [-1, 1.], name),  (0., [-1, 1., 1], name)...
    (True, name)

    For keyboard-driven controls, use KeyboardControl(...) directly.
    """

    if isinstance(short_params, bool):
        control = Control(short_params, name=param_name)
        control._auto_named = True
        return control
    if not isinstance(short_params, (tuple, list)):
        raise TypeError(f"issue with {param_name}, {short_params}")
    value_default = short_params[0]
    first_value_is_default_val = default_value_check(value_default)
    name = None
    step = None
    group = None
    scale = "linear"
    if isinstance(value_default, bool):
        # BOOLEAN: (bool, name, group)
        # No keyboard support in abbreviations - use KeyboardControl directly
        value_range = None
        if len(short_params) >= 2:
            name = short_params[1]
            if name is not None and not isinstance(name, str):
                raise TypeError(
                    f"{name} name shall be a string or None: "
                    "you do not need to provide a value range for a boolean slider."
                )

        if len(short_params) > 3:
            raise ValueError(
                f"Boolean abbreviation has too many elements: {short_params}. "
                "Expected: (bool, name, group). "
                "For keyboard controls, use KeyboardControl(...) directly."
            )

        # Check for group (3rd element)
        if len(short_params) == 3:
            group = short_params[2]
            if group is not None:
                from interactive_pipe.headless.panel import Panel

                if not isinstance(group, (str, Panel)):
                    raise TypeError(_group_error(group))
    else:
        if first_value_is_default_val:
            # INT/FLOAT/STR
            start = 1
            if len(short_params) < 2:
                raise ValueError("providing a value range is mandatory like (min, max) or (min, max, step)")
            value_range = short_params[start]
            if value_range is None:
                pass
            else:
                if not isinstance(value_range, (list, tuple)):
                    raise TypeError(f"value range should be a tuple or a list, provided {value_range}")
                if isinstance(value_default, (float, int)) and len(value_range) > 3:
                    raise ValueError(
                        f"range {list(value_range)} has too many elements: write [min, max] or [min, max, step] "
                        "(the default is the first element of the tuple)"
                    )
                if isinstance(value_default, (float, int)) and len(value_range) >= 3:
                    step = value_range[2]
                    value_range = value_range[:2]
                    if step == "log":  # (1e-2, [1e-4, 1e-1, "log"]): a log slider
                        step, scale = None, "log"
        else:
            # ["cat", "dog", "tree"] -> default value = "cat"
            # [-10, 10, 1] -> default val = average(-10, 10), step=1
            # [-10, 10] -> default val = average(-10, 10)
            # [-10, 10, 1/None, 5], default val = 5, step=None
            value_default = None
            start = 0
            special_list = short_params[0]
            if len(special_list) == 0:
                raise ValueError("cannot provide an empty list or tuple")

            if all(isinstance(item, str) for item in special_list):
                # ["cat", "dog", "tree"] -> default value = "cat"
                value_default = special_list[0]
                value_range = special_list
            elif isinstance(special_list[0], (int, float)):
                if len(special_list) < 2:
                    raise ValueError("please provide [min, max], [min, max, step], [min, max, None, default]")
                if len(special_list) > 4:
                    raise ValueError(
                        f"{special_list}: at most 4 values, [min, max, step, default] (got {len(special_list)})"
                    )
                if not isinstance(special_list[1], (int, float)):
                    raise TypeError(
                        f"min={special_list[0]} max={special_list[1]} - max parameter should be numerical too"
                    )
                value_range = special_list[:2]

                if len(special_list) >= 3:
                    # [-10, 10, 1] -> default val = average(-10, 10), step=1
                    step = special_list[2]
                    if step == "log":  # [1e-4, 1e-1, "log"]: a log slider
                        step, scale = None, "log"
                    if step is not None and not isinstance(step, (int, float)):
                        raise TypeError(f"{step} has to be numerical")
                    if len(special_list) == 4:
                        # [-10, 10, 1] -> default val = average(-10, 10), step=1
                        value_default = special_list[3]
                if value_default is None and scale == "log":
                    value_default = float(f"{(value_range[0] * value_range[1]) ** 0.5:.3g}")  # geometric middle
                if value_default is None:
                    if isinstance(value_range[0], int) and isinstance(value_range[1], int):
                        value_default = (value_range[0] + value_range[1]) // 2
                    else:
                        value_default = (value_range[0] + value_range[1]) / 2.0
            else:
                raise ValueError(f"wrong abbreviation {special_list}")

        # Numeric/String: (default, range, name, group)
        # No keyboard support in abbreviations - use KeyboardControl directly
        if len(short_params) >= start + 2:
            name = short_params[start + 1]

        if len(short_params) > start + 3:
            raise ValueError(
                f"Control abbreviation has too many elements: {short_params}. "
                f"Expected: (default, range, name, group). "
                "For keyboard controls, use KeyboardControl(...) directly."
            )

        # Check for group (4th element for default-first, 3rd for list-first)
        if len(short_params) == start + 3:
            group = short_params[start + 2]
            if group is not None:
                from interactive_pipe.headless.panel import Panel

                if not isinstance(group, (str, Panel)):
                    raise TypeError(_group_error(group))

    auto_named = name is None
    if name is None:
        name = param_name

    # Convert value_range tuple to list if needed for type checking
    if value_range is not None and isinstance(value_range, tuple):
        value_range_list: Optional[List[Union[int, float, str]]] = list(value_range)
        value_range = value_range_list

    # Keyboard controls are no longer supported via abbreviations
    # Users should use KeyboardControl(...) directly
    control = Control(value_default, value_range=value_range, name=name, step=step, group=group, scale=scale)
    # named after the parameter, not by the user: may be disambiguated in a pipeline
    control._auto_named = control._auto_named or auto_named
    return control
