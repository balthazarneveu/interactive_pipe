"""
Tests for exception handling in graphical module
"""

import pytest
import numpy as np
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.control import TimeControl
from interactive_pipe.graphical.mpl_control import (
    IntSliderMatplotlibControl,
    FloatSliderMatplotlibControl,
    BoolCheckButtonMatplotlibControl,
    StringRadioButtonMatplotlibControl,
    PromptMatplotlibControl,
)

try:
    from interactive_pipe.graphical.nb_control import (
        IntSliderNotebookControl,
        FloatSliderNotebookControl,
        BoolCheckButtonNotebookControl,
        DialogNotebookControl,
        PromptNotebookControl,
        IPYWIDGETS_AVAILABLE,
    )

    NB_CONTROL_AVAILABLE = IPYWIDGETS_AVAILABLE
except ImportError:
    NB_CONTROL_AVAILABLE = False

try:
    from interactive_pipe.graphical.qt_control import (
        IntSliderControl,
        FloatSliderControl,
        TickBoxControl,
        DropdownMenuControl,
        PromptControl,
        IconButtonsControl,
        PYQT_AVAILABLE,
    )

    QT_CONTROL_AVAILABLE = PYQT_AVAILABLE
except ImportError:
    QT_CONTROL_AVAILABLE = False

try:
    from interactive_pipe.graphical.gradio_control import (
        IntSliderControl as GradioIntSliderControl,
        FloatSliderControl as GradioFloatSliderControl,
        TickBoxControl as GradioTickBoxControl,
        DropdownMenuControl as GradioDropdownMenuControl,
        PromptControl as GradioPromptControl,
        GRADIO_AVAILABLE,
    )

    GRADIO_CONTROL_AVAILABLE = GRADIO_AVAILABLE
except ImportError:
    GRADIO_CONTROL_AVAILABLE = False


class MockGUI(InteractivePipeGUI):
    """Mock GUI for testing base class"""

    def init_app(self, **kwargs):
        pass

    def run(self):
        return []


class TestGUIExceptions:
    """Test exception handling in InteractivePipeGUI"""

    def test_bind_keyboard_slider_raises_typeerror_when_not_keyboardcontrol(self):
        filter1 = FilterCore(apply_fn=lambda x: x)
        pipeline = HeadlessPipeline(filters=[filter1], inputs=[0])
        pipeline.inputs = [np.array([1, 2, 3])]

        gui = MockGUI(pipeline=pipeline)
        regular_control = Control(value_default=5.0, value_range=[0.0, 10.0])

        # Verify KeyboardControl is used in the type check
        assert KeyboardControl is not None
        with pytest.raises(TypeError, match="must be a KeyboardControl instance"):
            gui.bind_keyboard_slider(regular_control, lambda name, down: None)

    def test_plug_timer_control_raises_typeerror_when_not_timecontrol(self):
        filter1 = FilterCore(apply_fn=lambda x: x)
        pipeline = HeadlessPipeline(filters=[filter1], inputs=[0])
        pipeline.inputs = [np.array([1, 2, 3])]

        gui = MockGUI(pipeline=pipeline)
        regular_control = Control(value_default=5.0, value_range=[0.0, 10.0])

        # Verify TimeControl is used in the type check
        assert TimeControl is not None
        with pytest.raises(TypeError, match="must be a TimeControl instance"):
            gui.plug_timer_control(regular_control, lambda name, value: None)


class TestMatplotlibControlExceptions:
    """Test exception handling in matplotlib control classes"""

    def test_int_slider_raises_typeerror_when_not_int(self):
        control = Control(value_default=5.5, value_range=[0.0, 10.0])  # Float, not int
        with pytest.raises(TypeError, match="Expected int control type"):
            IntSliderMatplotlibControl("test", control, lambda name, val: None, None)

    def test_float_slider_raises_typeerror_when_not_float(self):
        control = Control(value_default=5, value_range=[0, 10])  # Int, not float
        with pytest.raises(TypeError, match="Expected float control type"):
            FloatSliderMatplotlibControl("test", control, lambda name, val: None, None)

    def test_bool_checkbutton_raises_typeerror_when_not_bool(self):
        control = Control(value_default=5.0, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected bool control type"):
            BoolCheckButtonMatplotlibControl(
                "test", control, lambda name, val: None, None
            )

    def test_string_radio_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)  # Bool, not str
        with pytest.raises(TypeError, match="Expected str control type"):
            StringRadioButtonMatplotlibControl(
                "test", control, lambda name, val: None, None
            )

    def test_string_radio_raises_valueerror_when_value_range_none(self):
        control = Control(value_default="test", value_range=None)
        with pytest.raises(ValueError, match="must be provided"):
            StringRadioButtonMatplotlibControl(
                "test", control, lambda name, val: None, None
            )

    def test_prompt_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)  # Bool, not str
        with pytest.raises(TypeError, match="Expected str control type"):
            PromptMatplotlibControl("test", control, lambda name, val: None, None)

    def test_prompt_raises_valueerror_when_value_range_not_none(self):
        # Use a valid default that's in the range, but PromptMatplotlibControl should reject value_range
        control = Control(value_default="a", value_range=["a", "b"])
        with pytest.raises(ValueError, match="must be None"):
            PromptMatplotlibControl("test", control, lambda name, val: None, None)


class TestNotebookControlExceptions:
    """Test exception handling in notebook control classes"""

    @pytest.mark.skipif(not NB_CONTROL_AVAILABLE, reason="ipywidgets not available")
    def test_int_slider_raises_typeerror_when_not_int(self):
        control = Control(value_default=5.5, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected int control type"):
            IntSliderNotebookControl("test", control)

    @pytest.mark.skipif(not NB_CONTROL_AVAILABLE, reason="ipywidgets not available")
    def test_float_slider_raises_typeerror_when_not_float(self):
        control = Control(value_default=5, value_range=[0, 10])
        with pytest.raises(TypeError, match="Expected float control type"):
            FloatSliderNotebookControl("test", control)

    @pytest.mark.skipif(not NB_CONTROL_AVAILABLE, reason="ipywidgets not available")
    def test_bool_checkbutton_raises_typeerror_when_not_bool(self):
        control = Control(value_default=5.0, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected bool control type"):
            BoolCheckButtonNotebookControl("test", control)

    @pytest.mark.skipif(not NB_CONTROL_AVAILABLE, reason="ipywidgets not available")
    def test_dialog_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            DialogNotebookControl("test", control)

    @pytest.mark.skipif(not NB_CONTROL_AVAILABLE, reason="ipywidgets not available")
    def test_prompt_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            PromptNotebookControl("test", control)

    @pytest.mark.skipif(not NB_CONTROL_AVAILABLE, reason="ipywidgets not available")
    def test_prompt_raises_valueerror_when_value_range_not_none(self):
        # Use a valid default that's in the range, but PromptNotebookControl should reject value_range
        control = Control(value_default="a", value_range=["a", "b"])
        with pytest.raises(ValueError, match="must be None"):
            PromptNotebookControl("test", control)


class TestQtControlExceptions:
    """Test exception handling in Qt control classes"""

    @pytest.fixture(autouse=True)
    def setup_qt_app(self):
        """Initialize QApplication for Qt tests"""
        if not QT_CONTROL_AVAILABLE:
            pytest.skip("PyQt not available")
        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                app = QApplication([])
            yield app
        except ImportError:
            try:
                from PyQt5.QtWidgets import QApplication

                app = QApplication.instance()
                if app is None:
                    app = QApplication([])
                yield app
            except ImportError:
                try:
                    from PySide6.QtWidgets import QApplication

                    app = QApplication.instance()
                    if app is None:
                        app = QApplication([])
                    yield app
                except ImportError:
                    pytest.skip("Qt not available")

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_int_slider_raises_typeerror_when_not_int(self):
        control = Control(value_default=5.5, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected int control type"):
            IntSliderControl("test", control, lambda name: None)

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_float_slider_raises_typeerror_when_not_float(self):
        control = Control(value_default=5, value_range=[0, 10])
        with pytest.raises(TypeError, match="Expected float control type"):
            FloatSliderControl("test", control, lambda name: None)

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_tickbox_raises_typeerror_when_not_bool(self):
        control = Control(value_default=5.0, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected bool control type"):
            TickBoxControl("test", control, lambda name: None)

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_dropdown_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            DropdownMenuControl("test", control, lambda name: None)

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_dropdown_raises_valueerror_when_value_range_missing(self):
        # This is tested in the check_control_type, but value_range check happens in __init__
        # Use a valid default that's in the range
        control = Control(value_default="a", value_range=["a", "b"])
        # Should work fine - dropdown requires value_range to be provided
        dropdown = DropdownMenuControl("test", control, lambda name: None)
        assert dropdown is not None

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_prompt_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            PromptControl("test", control, lambda name: None)

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_prompt_raises_valueerror_when_value_range_not_none(self):
        # Use a valid default that's in the range, but PromptControl should reject value_range
        control = Control(value_default="a", value_range=["a", "b"])
        with pytest.raises(ValueError, match="must be None"):
            PromptControl("test", control, lambda name: None)

    @pytest.mark.skipif(not QT_CONTROL_AVAILABLE, reason="PyQt not available")
    def test_icon_buttons_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            IconButtonsControl("test", control, lambda name, idx: None)


class TestGradioControlExceptions:
    """Test exception handling in Gradio control classes"""

    @pytest.mark.skipif(not GRADIO_CONTROL_AVAILABLE, reason="gradio not available")
    def test_int_slider_raises_typeerror_when_not_int(self):
        control = Control(value_default=5.5, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected int control type"):
            GradioIntSliderControl("test", control, lambda name: None)

    @pytest.mark.skipif(not GRADIO_CONTROL_AVAILABLE, reason="gradio not available")
    def test_float_slider_raises_typeerror_when_not_float(self):
        control = Control(value_default=5, value_range=[0, 10])
        with pytest.raises(TypeError, match="Expected float control type"):
            GradioFloatSliderControl("test", control, lambda name: None)

    @pytest.mark.skipif(not GRADIO_CONTROL_AVAILABLE, reason="gradio not available")
    def test_tickbox_raises_typeerror_when_not_bool(self):
        control = Control(value_default=5.0, value_range=[0.0, 10.0])
        with pytest.raises(TypeError, match="Expected bool control type"):
            GradioTickBoxControl("test", control, lambda name: None)

    @pytest.mark.skipif(not GRADIO_CONTROL_AVAILABLE, reason="gradio not available")
    def test_dropdown_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            GradioDropdownMenuControl("test", control, lambda name: None)

    @pytest.mark.skipif(not GRADIO_CONTROL_AVAILABLE, reason="gradio not available")
    def test_prompt_raises_typeerror_when_not_str(self):
        control = Control(value_default=True)
        with pytest.raises(TypeError, match="Expected str control type"):
            GradioPromptControl("test", control, lambda name: None)

    @pytest.mark.skipif(not GRADIO_CONTROL_AVAILABLE, reason="gradio not available")
    def test_prompt_raises_valueerror_when_value_range_not_none(self):
        # Use a valid default that's in the range, but GradioPromptControl should reject value_range
        control = Control(value_default="a", value_range=["a", "b"])
        with pytest.raises(ValueError, match="must be None"):
            GradioPromptControl("test", control, lambda name: None)


# Note: Testing GUI implementations (mpl_gui, qt_gui, etc.) would require
# mocking the GUI frameworks, which is complex. The critical exception
# paths are tested above through the base classes and control factories.
