import copy

from cache import CachedResults
from sliders import KeyboardSlider


class Filter:
    """
    Image processing single block is defined by the `apply` function to process multiple images
    """

    def __init__(self, name, sliders=None, inputs=[0], outputs=[0], cache=True):
        self.name = name
        self.cache = cache
        self.inputs = inputs
        self.outputs = outputs
        self.global_params = {}
        self.cursor = None
        self.cursor_cbk = None
        self.reset_cache()
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

    def __repr__(self):
        descr = "%s\n" % self.name
        if not (self.inputs == [0] and self.outputs == [0]):
            descr += "(" + (",".join(["%d" % it for it in self.inputs])) + ")"
            descr += "->" + \
                "(" + ",".join(["%d" % it for it in self.outputs]) + ")\n"
        for idx, sname in enumerate(self.sliderslist):
            descr += "\t%s=%.3f" % (sname, self.values[idx])
        descr += "\n"
        return descr

    def apply(self, *imgs, **kwargs) -> list:
        """
        :param imgs: img0, img1, img2, value1 , value2 , value3 ....
            - (img0 is the result from the previous step)
            - indexes of images processed is defined by `self.inputs`
            - indexes of output images to be processed are defined by `self.outputs`
            - then follow the parameters to be applied  `self.values` depicted by `self.sliderslist`
        :param kwargs: dictionary containing all parameters
        :return: output1, output2 ...
        """
        raise NotImplementedError("Need to implement the apply method")

    def set_global_params(self, global_params: dict):
        self.global_params = global_params

    def set_cursor(self, cursor):
        self.cursor = cursor

    def reset_cache(self):
        if self.cache:
            self.cache_mem = CachedResults(self.name)
        else:
            self.cache_mem = None
