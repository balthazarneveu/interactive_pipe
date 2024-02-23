import pytest

from interactive_pipe.headless.control import Control


def test_control_init():
    with pytest.raises(AssertionError):
        ctrl = Control("foot", ["boo", "foo", "bar"])
    with pytest.raises(AssertionError):
        ctrl = Control(4, ["boo", "foo"])
    with pytest.raises(AssertionError):
        ctrl = Control(4, [7, 8, 9])
    ctrl = Control("foo", ["boo", "foo", "bar"])
    with pytest.raises(AssertionError):
        ctrl.value = "hop"
    print(ctrl)
    ctrl.value = "bar"
    print(ctrl)
    ctrl.reset()
    print(ctrl)
    ctrl = Control(4, [0.5, 8])
    print(ctrl)
    with pytest.raises(AssertionError):
        ctrl = Control(4, [0, 1])
    ctrl = Control(4, [0, 8])
    print(ctrl)
    ctrl.value = 28
    print(ctrl)
    ctrl = Control(68)
    ctrl.value = 42
    print(ctrl)
    ctrl.reset()
    print(ctrl)
