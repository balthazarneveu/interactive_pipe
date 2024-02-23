from interactive_pipe.headless.control import Control
from typing import Union, List, Optional
from interactive_pipe.core.filter import FilterCore


class KeyboardControl(Control):
    """
    Plug and play class to replace a slider by keyboard interaction
    """
    KEY_UP = "up"
    KEY_DOWN = "down"
    KEY_LEFT = "left"
    KEY_RIGHT = "right"
    KEY_PAGEUP = "pageup"
    KEY_PAGEDOWN = "pagedown"
    KEY_SPACEBAR = " "
    SPECIAL_KEYS_LIST = [KEY_UP, KEY_DOWN, KEY_PAGEDOWN, KEY_LEFT, KEY_RIGHT,
                         KEY_PAGEUP, KEY_PAGEDOWN, KEY_SPACEBAR] + [f"f{i}" for i in range(1, 13)]

    def __init__(self, value_default: Union[int, float, bool, str], value_range: List[Union[int, float, str]] = None, keydown=None, keyup=None, modulo=False, name=None, step=None, filter_to_connect: Optional[FilterCore] = None, parameter_name_to_connect: Optional[str] = None) -> None:
        super().__init__(value_default=value_default, value_range=value_range, name=name, step=step,
                         filter_to_connect=filter_to_connect, parameter_name_to_connect=parameter_name_to_connect, icons=None)
        self.keyup = keyup
        self.keydown = keydown
        self.modulo = modulo

    def on_key(self, down=True):
        if self._type == bool:
            new_val = not self.value
            self.value = new_val
            return
        if self._type == int or self._type == float:
            current_val = self.value
            sign = (-1 if down else +1)
            step = self.step
            mini, maxi = self.value_range[0], self.value_range[1]
        elif self._type == str:
            current_val = self.value_range.index(self.value)
            sign = (-1 if down else +1)
            step = 1
            mini, maxi = 0, len(self.value_range)-1
        new_val = current_val + sign*step
        if new_val > maxi:
            new_val = mini if self.modulo else maxi
        if new_val < mini:
            new_val = maxi if self.modulo else mini
        if self._type == str:
            new_val = self.value_range[new_val]
        self.value = new_val

    def on_key_down(self):
        self.on_key(down=True)

    def on_key_up(self):
        if self.keyup is not None:
            self.on_key(down=False)

    def __repr__(self) -> str:
        return super().__repr__() + f" | down:{'' if self.keydown is None else self.keydown} |  up:{'' if self.keyup is None else self.keyup}  | modulo:{self.modulo}"

    @staticmethod
    def sanity_check_key(key):
        assert isinstance(key, str), f"{key} shall be a string"
        key = key.lower()
        assert len(key) > 0
        if len(key) > 1:
            assert key in KeyboardControl.SPECIAL_KEYS_LIST, f"{key} is not supported - use {KeyboardControl.SPECIAL_KEYS_LIST}"
        return key
