class SliderSimple:
    def __init__(self, default_value, minimum, maximum, step=None, pretty_name=None, **kwargs) -> None:
        self.default_value = default_value
        self.vrange = [minimum, maximum]
        self.step = step
        self.pretty_name = pretty_name

# TODO: avoid repetitions between Slider(float) and SliderSimple
class Slider(float):
    """
    More than a float...
    Slider can be interpreted as a simple float when used in arithmetic operations
    But has many more fields such as a classic slider
    """
    def __new__(cls, default_value, minimum, maximum, pretty_name=None, step=None, **kwargs):
        return float.__new__(cls, default_value)

    def __init__(self, default_value, minimum, maximum, pretty_name=None, step=None, **kwargs):
        self.default_value = default_value
        self.vrange = [minimum, maximum]
        self.step = step
        self.pretty_name = pretty_name
        self.kwargs = kwargs

    def __reduce__(self):
        return (self.__class__, (self.default_value, self.vrange[0], self.vrange[1], self.pretty_name, self.step), self.kwargs)
    def __repr__(self) -> str:
        return f"{self.default_value} in [{self.vrange}]"

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
