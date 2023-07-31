class KeyboardSlider:
    """
    Class to replace a slider by keyboard interaction
    """

    def __init__(self, vrange, keydown, keyup=None, increment=None, modulo=False):
        self.vrange = vrange
        self.keyup = keyup
        self.keydown = keydown
        if modulo:
            assert increment is None, "Do not specify increment when using modulo"
            increment = 1 / (vrange[1] - vrange[0] + 1)
        else:
            if increment is None:
                increment = 1 / 100.
        self.modulo = modulo
        if keyup is None and not modulo:
            self.increment = None
            for el in vrange:
                assert isinstance(
                    el, bool), f"toogle slider needs booleans in {vrange}"
        else:
            self.increment = increment
