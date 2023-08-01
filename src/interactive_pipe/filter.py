import copy
from typing import List

from core import FilterCore
from sliders import KeyboardSlider


class Filter(FilterCore):
    """
    Image processing single block is defined by the `apply` function to process multiple images
    """

    def __init__(self, name=None, sliders: dict = None, inputs: List[int] = [0], outputs: List[int] = [0], cache=True):
        super().__init__(name=name, inputs=inputs, outputs=outputs, cache=cache)
        self.cursor = None
        self.cursor_cbk = None
        if sliders is None:
            sliders = self.get_default_sliders()
        if sliders is not None:
            assert isinstance(sliders, dict)
            sliderslist, vrange = [], []
            for sli_name, sli_val in sliders.items():
                sliderslist.append(sli_name)
                vrange.append(sli_val)
        assert isinstance(sliderslist, list)
        self.sliderslist = sliderslist
        self.defaultvalue = []
        self.vrange = []
        self.slidertype = []
        for _vr in vrange:
            if isinstance(_vr, KeyboardSlider):
                vr = _vr.vrange
                self.slidertype.append(_vr)
            else:
                vr = _vr
                self.slidertype.append(None)
            if len(vr) == 2:
                self.vrange.append(vr)
                self.defaultvalue.append(0.)
            elif len(vr) == 3:
                self.vrange.append(vr[0:2])
                self.defaultvalue.append(vr[2])
        self.values = copy.deepcopy(self.defaultvalue)

    def get_default_sliders(self) -> dict:
        """Useful to define default sliders"""
        return {}

    def set_cursor(self, cursor):
        self.cursor = cursor

    def __repr__(self) -> str:
        descr = super().__repr__()[:-1]
        for idx, sname in enumerate(self.sliderslist):
            descr += "\t%s=%.3f" % (sname, self.values[idx])
        descr += "\n"
        return descr
