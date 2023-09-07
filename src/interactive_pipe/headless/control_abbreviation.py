from interactive_pipe.core.control import Control

def control_from_tuple(short_params, param_name :str =None):
    '''
    (0., [-1, 1.], name),  (0., [-1, 1., 1], name)...
    (True, name)
    '''
    if isinstance(short_params, bool):
        return Control(short_params, name=param_name)
    assert isinstance(short_params, tuple) or isinstance(short_params, list), f"issue with {param_name}, {short_params}"
    value_default = short_params[0]
    name = None
    step = None
    if isinstance(value_default, bool):
        value_range = None
        if len(short_params) >= 2:
            name = short_params[1]
    else:
        assert len(short_params) >= 2
        value_range = short_params[1]
        assert isinstance(value_range, list) or isinstance(value_range, tuple)
        if (isinstance(value_default, float) or isinstance(value_default, int)) and len(value_range)>=3:
            step = value_range[2]
            value_range = value_range[:2]
        if len(short_params) >= 3:
            name = short_params[2]
    if name is None:
        name=param_name
    return Control(value_default, value_range=value_range, name=name, step=step)