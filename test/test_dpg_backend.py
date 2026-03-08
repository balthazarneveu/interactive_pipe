"""Tests for Dear PyGui backend."""

import numpy as np
import pytest

# Try to import DPG - tests will be skipped if not available
try:
    import dearpygui.dearpygui  # noqa: F401

    DPG_AVAILABLE = True
except ImportError:
    DPG_AVAILABLE = False

from interactive_pipe.headless.control import Control

if DPG_AVAILABLE:
    import dearpygui.dearpygui as dpg

    from interactive_pipe.graphical.dpg_control import (
        ControlFactory,
        DropdownMenuControl,
        FloatSliderControl,
        IntSliderControl,
        PromptControl,
        TickBoxControl,
    )
    from interactive_pipe.graphical.dpg_gui import MainWindow

from interactive_pipe.headless.panel import Panel


@pytest.mark.skipif(not DPG_AVAILABLE, reason="DearPyGui not installed")
class TestDPGControls:
    """Test DPG control creation."""

    def test_control_factory_int_slider(self):
        """Test creating an integer slider control."""
        ctrl = Control(name="test_int", value_range=[0, 100], value_default=50)

        def dummy_update(name, value):
            pass

        factory = ControlFactory()
        control = factory.create_control(ctrl, dummy_update)

        assert control is not None
        assert isinstance(control, IntSliderControl)
        assert control.name == "test_int"

    def test_control_factory_float_slider(self):
        """Test creating a float slider control."""
        ctrl = Control(name="test_float", value_range=[0.0, 1.0], value_default=0.5)

        def dummy_update(name, value):
            pass

        factory = ControlFactory()
        control = factory.create_control(ctrl, dummy_update)

        assert control is not None
        assert isinstance(control, FloatSliderControl)
        assert control.name == "test_float"

    def test_control_factory_checkbox(self):
        """Test creating a checkbox control."""
        ctrl = Control(name="test_bool", value_default=True)

        def dummy_update(name, value):
            pass

        factory = ControlFactory()
        control = factory.create_control(ctrl, dummy_update)

        assert control is not None
        assert isinstance(control, TickBoxControl)
        assert control.name == "test_bool"

    def test_control_factory_dropdown(self):
        """Test creating a dropdown control."""
        ctrl = Control(name="test_dropdown", value_range=["A", "B", "C"], value_default="A")

        def dummy_update(name, value):
            pass

        factory = ControlFactory()
        control = factory.create_control(ctrl, dummy_update)

        assert control is not None
        assert isinstance(control, DropdownMenuControl)
        assert control.name == "test_dropdown"

    def test_control_factory_text_input(self):
        """Test creating a text input control."""
        ctrl = Control(name="test_text", value_default="hello")

        def dummy_update(name, value):
            pass

        factory = ControlFactory()
        control = factory.create_control(ctrl, dummy_update)

        assert control is not None
        assert isinstance(control, PromptControl)
        assert control.name == "test_text"

    def test_control_factory_single_value_returns_none(self):
        """Test that single-value controls return None (no widget)."""
        ctrl = Control(name="test_single", value_range=["A"], value_default="A")

        def dummy_update(name, value):
            pass

        factory = ControlFactory()
        control = factory.create_control(ctrl, dummy_update)

        assert control is None


@pytest.mark.skipif(not DPG_AVAILABLE, reason="DearPyGui not installed")
class TestImageConversion:
    """Test image conversion utilities."""

    def test_convert_grayscale_to_rgba(self):
        """Test converting grayscale image to RGBA."""
        img = np.random.rand(10, 10).astype(np.float32)
        converted = MainWindow.convert_image_to_dpg(img)

        # Should be flattened RGBA
        assert len(converted) == 10 * 10 * 4

    def test_convert_rgb_to_rgba(self):
        """Test converting RGB image to RGBA."""
        img = np.random.rand(10, 10, 3).astype(np.float32)
        converted = MainWindow.convert_image_to_dpg(img)

        # Should be flattened RGBA
        assert len(converted) == 10 * 10 * 4

    def test_convert_rgba_unchanged(self):
        """Test that RGBA image is flattened but not changed."""
        img = np.random.rand(10, 10, 4).astype(np.float32)
        converted = MainWindow.convert_image_to_dpg(img)

        # Should be flattened RGBA
        assert len(converted) == 10 * 10 * 4

    def test_clipping_to_01_range(self):
        """Test that image values are clipped to 0-1 range."""
        img = np.array([[-0.5, 0.5], [1.5, 2.0]]).astype(np.float32)
        converted = MainWindow.convert_image_to_dpg(img)

        # Convert back to numpy for checking
        converted_array = np.array(converted).reshape(2, 2, 4)

        # Check that values are in 0-1 range
        assert np.all(converted_array >= 0.0)
        assert np.all(converted_array <= 1.0)

        # Check clipping worked
        assert converted_array[0, 0, 0] == 0.0  # -0.5 clipped to 0
        assert converted_array[1, 1, 0] == 1.0  # 2.0 clipped to 1


@pytest.mark.skip(reason="Requires display - DPG viewport/destroy_context not headless-safe")
@pytest.mark.skipif(not DPG_AVAILABLE, reason="DearPyGui not installed")
def test_dpg_panel_layout_builds():
    """Panel positions and grid layout build without error.

    Run manually with display to verify: create MainWindow with panels at
    top/left/right/bottom and grid layout; or run demo/image_editing_demo.py -b dpg.
    """
    dpg.create_context()

    class MockPipeline:
        def __init__(self):
            self.global_params = {}

    pipeline = MockPipeline()

    # Panels at different positions
    top_panel = Panel("Top", position="top")
    left_panel = Panel("Left", position="left")
    right_panel = Panel("Right", position="right")
    bottom_panel = Panel("Bottom", position="bottom")

    # Grid layout: row of two nested panels
    sub_a = Panel("SubA")
    sub_b = Panel("SubB")
    Panel("Grid").add_elements([[sub_a, sub_b]])

    ctrl_ungrouped = Control(name="ungrouped", value_range=[0, 1], value_default=0.5)
    ctrl_top = Control(name="top_ctrl", value_range=[0, 1], value_default=0.5, group=top_panel)
    ctrl_left = Control(name="left_ctrl", value_range=[0, 1], value_default=0.5, group=left_panel)
    ctrl_right = Control(name="right_ctrl", value_range=[0, 1], value_default=0.5, group=right_panel)
    ctrl_bottom = Control(name="bottom_ctrl", value_range=[0, 1], value_default=0.5, group=bottom_panel)
    ctrl_grid = Control(name="grid_ctrl", value_range=[0, 1], value_default=0.5, group=sub_a)

    controls = [ctrl_ungrouped, ctrl_top, ctrl_left, ctrl_right, ctrl_bottom, ctrl_grid]
    window = MainWindow(
        controls=controls,
        name="Panel test",
        pipeline=pipeline,
        size=(800, 600),
    )
    assert pipeline.global_params["__window"] is window
    assert hasattr(window, "top_panels_tag")
    assert hasattr(window, "left_panels_tag")
    assert hasattr(window, "right_panels_tag")
    dpg.destroy_context()


# Integration test - requires display, marked as manual
@pytest.mark.skip(reason="Requires display - manual test only")
@pytest.mark.skipif(not DPG_AVAILABLE, reason="DearPyGui not installed")
def test_dpg_backend_integration():
    """Integration test for DPG backend (requires display)."""
    from interactive_pipe import interactive

    @interactive(brightness=(0.5, [0.0, 2.0], "Brightness"))
    def adjust_brightness(img, brightness=0.5):
        return img * brightness

    def pipeline(img_list):
        img = img_list[0]
        adjusted = adjust_brightness(img)
        return [img, adjusted]

    # This would require user interaction to test properly
    # Example usage:
    # test_img = np.random.rand(256, 256, 3).astype(np.float32)
    # gui = interactive_pipeline(pipeline, gui="dpg", name="DPG Test")
    # result = gui([test_img])
