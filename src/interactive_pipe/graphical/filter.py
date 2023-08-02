import copy
from typing import List, Callable

from core.filter import FilterCore
from core.sliders import KeyboardSlider, Slider


class Filter(FilterCore):
    """
    Image processing single block is defined by the `apply` function to process multiple images
    """

    def __init__(self, apply_fn=None, name=None, sliders: dict = None, inputs: List[int] = [0], outputs: List[int] = [0], cache=True):
        super().__init__(apply_fn=apply_fn, name=name,
                         inputs=inputs, outputs=outputs, cache=cache)
        self.cursor = None
        self.cursor_cbk = None
        if sliders is None:
            sliders = self.get_default_sliders()
        assert sliders is not None
        assert isinstance(sliders, dict)
        sliderslist, vrange, defaultvalue, value = [], [], [], {}
        for sli_name, sli_val in sliders.items():
            if sli_name == "global_params":
                continue
            sliderslist.append(sli_name)
            vrange.append(sli_val)
            value[sli_name] = sli_val
            defaultvalue.append(sli_val[0])
        # FIXME: there's a very ugly mapping between slider_values (a list) & values (dictionary)
        self.values = copy.deepcopy(value)
        self.defaultvalue = copy.deepcopy(defaultvalue)
        self.slider_values = copy.deepcopy(defaultvalue)
        self.sliderslist = sliderslist
        self.vrange = []
        self.slidertype = []
        for _vr in vrange:
            if isinstance(_vr, KeyboardSlider):
                vr = _vr.vrange
                self.slidertype.append(_vr)
            else:
                vr = _vr
                self.slidertype.append(None)
            self.vrange.append(vr[1:])

    def get_default_sliders(self) -> dict:
        """Useful to define default sliders"""
        return {}

    def set_cursor(self, cursor):
        self.cursor = cursor

    def __repr__(self) -> str:
        descr = super().__repr__()[:-1]
        for idx, sname in enumerate(self.sliderslist):
            descr += f"{sname}: {self.values}"
        descr += "\n"
        return descr


class AutoFilter(FilterCore):
    def __init__(self, apply_fn: Callable = None, inputs=None, outputs=None, name: str = None, cache: bool = True):
        assert apply_fn is not None
        # @TODO: use self.check_apply_signature here!
        args_names, kwargs_names = self.analyze_apply_fn_signature(apply_fn)
        assert (len(inputs) if inputs else 0) == len(args_names)
        outputs = []
        default_params = {}
        for key, val in kwargs_names.items():
            if "global_params" in key:
                continue
            if isinstance(val, int) or isinstance(val, float) or isinstance(val, bool):
                default_params[key] = val
            elif isinstance(val, Slider):
                default_params[key] = val.default_value
        super().__init__(apply_fn=apply_fn, name=name, inputs=inputs,
                         outputs=outputs, cache=cache, default_params=default_params)
