import pytest

from interactive_pipe.headless.control import (
    Control,
    CircularControl,
    TextPrompt,
    TimeControl,
)


def test_control_init():
    with pytest.raises(ValueError):
        ctrl = Control("foot", ["boo", "foo", "bar"])
    with pytest.raises(TypeError):
        ctrl = Control(4, ["boo", "foo"])
    with pytest.raises(ValueError):
        ctrl = Control(4, [7, 8, 9])
    ctrl = Control("foo", ["boo", "foo", "bar"])
    with pytest.raises(ValueError):
        ctrl.value = "hop"
    print(ctrl)
    ctrl.value = "bar"
    print(ctrl)
    ctrl.reset()
    print(ctrl)
    ctrl = Control(4, [0.5, 8])
    print(ctrl)
    with pytest.raises(ValueError):
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


def test_control_tooltip_basic():
    """Test that Control accepts and stores tooltip parameter"""
    # Test tooltip with int control
    ctrl = Control(5, [0, 10], tooltip="This is a test tooltip")
    assert ctrl.tooltip == "This is a test tooltip"

    # Test tooltip with float control
    ctrl = Control(0.5, [0.0, 1.0], tooltip="Float slider tooltip")
    assert ctrl.tooltip == "Float slider tooltip"

    # Test tooltip with bool control
    ctrl = Control(True, tooltip="Boolean control tooltip")
    assert ctrl.tooltip == "Boolean control tooltip"

    # Test tooltip with string control (dropdown)
    ctrl = Control(
        "option1", ["option1", "option2", "option3"], tooltip="Dropdown tooltip"
    )
    assert ctrl.tooltip == "Dropdown tooltip"

    # Test tooltip with string control (text prompt)
    ctrl = Control("default text", tooltip="Text prompt tooltip")
    assert ctrl.tooltip == "Text prompt tooltip"


def test_control_tooltip_default_none():
    """Test that tooltip defaults to None for backward compatibility"""
    ctrl = Control(5, [0, 10])
    assert ctrl.tooltip is None

    ctrl = Control(True)
    assert ctrl.tooltip is None

    ctrl = Control("test", ["test", "test2"])
    assert ctrl.tooltip is None


def test_control_tooltip_with_name():
    """Test that tooltip works alongside other parameters like name"""
    ctrl = Control(5, [0, 10], name="My Control", tooltip="Control tooltip")
    assert ctrl.name == "My Control"
    assert ctrl.tooltip == "Control tooltip"


def test_circular_control_tooltip():
    """Test that CircularControl supports tooltip parameter"""
    ctrl = CircularControl(0, [0, 360], modulo=True, tooltip="Circular slider tooltip")
    assert ctrl.tooltip == "Circular slider tooltip"
    assert ctrl.modulo is True


def test_text_prompt_tooltip():
    """Test that TextPrompt supports tooltip parameter"""
    ctrl = TextPrompt("default", tooltip="Text prompt tooltip")
    assert ctrl.tooltip == "Text prompt tooltip"


def test_time_control_tooltip():
    """Test that TimeControl supports tooltip parameter"""
    ctrl = TimeControl(tooltip="Time control tooltip")
    assert ctrl.tooltip == "Time control tooltip"


def test_control_tooltip_empty_string():
    """Test that empty string tooltip is accepted"""
    ctrl = Control(5, [0, 10], tooltip="")
    assert ctrl.tooltip == ""


def test_control_tooltip_multiline():
    """Test that multiline tooltips are accepted"""
    multiline_tooltip = "Line 1\nLine 2\nLine 3"
    ctrl = Control(5, [0, 10], tooltip=multiline_tooltip)
    assert ctrl.tooltip == multiline_tooltip
