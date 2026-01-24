"""
Comprehensive demo showcasing all widget types, controls, and multi-image layouts.

This demo demonstrates:
- Float sliders (with range)
- Int sliders (with range)
- Bool checkboxes
- String dropdowns
- TextPrompt (text input)
- CircularControl (circular slider)
- KeyboardControl (keyboard shortcuts)
- Multi-image layouts (1x3, 2x2, 3x1, etc.)
"""

import numpy as np
from pathlib import Path
import argparse
from typing import List
from interactive_pipe import (
    interactive,
    Control,
    CircularControl,
    TextPrompt,
    KeyboardControl,
)
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.data_objects.image import Image

# Backend imports
BACKEND_OPTIONS = []
try:
    from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib
    BACKEND_OPTIONS.append("mpl")
except ImportError:
    InteractivePipeMatplotlib = None

try:
    from interactive_pipe.graphical.qt_gui import InteractivePipeQT
    BACKEND_OPTIONS.append("qt")
except ImportError:
    InteractivePipeQT = None

try:
    from interactive_pipe.graphical.nb_gui import InteractivePipeJupyter
    BACKEND_OPTIONS.append("nb")
except ImportError:
    InteractivePipeJupyter = None

try:
    from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio
    BACKEND_OPTIONS.append("gradio")
except ImportError:
    InteractivePipeGradio = None

InteractivePipeKivy = None

assert len(BACKEND_OPTIONS) > 0, "No backend available!"

def get_image_paths(img_folder: Path = Path(__file__).parent / "images"):
    """Get list of image paths"""
    img_list = sorted(list(img_folder.glob("*.png")))
    return img_list


# ============================================================================
# Interactive Filters - showcasing different widget types
# ============================================================================


@interactive(
    image_index=(0, [0, 3]),  # Int slider with range
    layout_mode=Control("last_output", ["row_1x4", "grid_2x2", "column_3x1", "grid_2x4", "last_output"]),  # String dropdown
)
def select_image(
    img_list: List[Path],
    image_index: int = 0,
    layout_mode: str = "last_output",
    global_params={},
) -> np.ndarray:
    """Select an image from the list"""
    idx = min(image_index, len(img_list) - 1)
    img = Image.load_image(str(img_list[idx]))
    title = f"Original {idx+1}/{len(img_list)}: {img_list[idx].stem}"
    global_params["__output_styles"]["original"] = {"title": title}
    # Store layout_mode in global_params for set_layout_outputs to use
    global_params["layout_mode"] = layout_mode
    return img


def set_layout_outputs(global_params={}):
    """Set pipeline.outputs based on layout_mode string in global_params
    
    This function modifies pipeline.outputs to control the image layout arrangement.
    The layout_mode string determines how images are arranged in the grid.
    
    The outputs use variable names (strings) matching the return statement variable names.
    """
    layout_mode = global_params.get("layout_mode", "last_output")
    pipeline = global_params.get("__pipeline")
    
    if pipeline is None:
        return
    
    # Define output layouts as 2D structures of variable names (strings)
    # Variable names must match the return statement variable names
    layouts = {
        "row_1x4": [
            ["original", "adjusted", "blurred", "thresholded"]
        ],
        "grid_2x2": [
            ["original", "adjusted"],
            ["blurred", "thresholded"],
        ],
        "column_3x1": [
            ["original"],
            ["adjusted"],
            ["blurred"],
        ],
        "grid_2x4": [
            ["original", "adjusted", "blurred", "thresholded"],
            ["transformed", "colored", "text_overlay", "noisy"],
        ],
        "last_output": [
            ["noisy"]  # Show only the last output (noisy)
        ],
    }
    
    # Set the pipeline outputs based on layout mode
    if layout_mode in layouts:
        pipeline.outputs = layouts[layout_mode]


@interactive(
    brightness=(0.0, [-1.0, 1.0]),  # Float slider: -1 (dark) to +1 (bright)
    contrast=(0.0, [-1.0, 1.0]),  # Float slider: -1 (low) to +1 (high)
)
def adjust_brightness_contrast(
    img: np.ndarray, brightness: float = 0.0, contrast: float = 0.0, global_params={}
) -> np.ndarray:
    """Adjust brightness and contrast"""
    # Apply brightness: add brightness value directly
    # brightness: -1.0 = very dark, 0.0 = no change, 1.0 = very bright
    bright_img = img + brightness
    
    # Apply contrast: stretch around midpoint (0.5)
    # contrast: -1.0 = low contrast, 0.0 = no change, 1.0 = high contrast
    # Formula: (img - 0.5) * (1 + contrast) + 0.5
    # When contrast=0: (img - 0.5) * 1 + 0.5 = img (no change)
    # When contrast=1: (img - 0.5) * 2 + 0.5 = 2*img - 0.5 (high contrast)
    # When contrast=-1: (img - 0.5) * 0 + 0.5 = 0.5 (low contrast, gray)
    contrasted_img = (bright_img - 0.5) * (1.0 + contrast) + 0.5
    
    # Clamp to valid range [0, 1]
    contrasted_img = np.clip(contrasted_img, 0.0, 1.0)
    
    title = f"Brightness: {brightness:+.2f}, Contrast: {contrast:+.2f}"
    global_params["__output_styles"]["adjusted"] = {"title": title}
    return contrasted_img


@interactive(
    blur_amount=CircularControl(3, [1, 15], modulo=True),  # CircularControl (int)
    enable_blur=(False,),  # Bool checkbox
)
def apply_blur(
    img: np.ndarray, blur_amount: int = 3, enable_blur: bool = False, global_params={}
) -> np.ndarray:
    """Apply blur effect"""
    if not enable_blur:
        global_params["__output_styles"]["blurred"] = {"title": "Blur: OFF"}
        return img
    
    # Simple box blur
    kernel_size = blur_amount * 2 + 1
    h, w, c = img.shape
    blurred = img.copy()
    
    # Apply horizontal blur
    for y in range(h):
        for x in range(w):
            x_start = max(0, x - blur_amount)
            x_end = min(w, x + blur_amount + 1)
            blurred[y, x] = img[y, x_start:x_end].mean(axis=0)
    
    # Apply vertical blur
    for y in range(h):
        for x in range(w):
            y_start = max(0, y - blur_amount)
            y_end = min(h, y + blur_amount + 1)
            blurred[y, x] = blurred[y_start:y_end, x].mean(axis=0)
    
    title = f"Blur: ON (radius={blur_amount})"
    global_params["__output_styles"]["blurred"] = {"title": title}
    return blurred


@interactive(
    threshold=(0.5, [0.0, 1.0]),  # Float slider
    invert=(False,),  # Bool checkbox
)
def apply_threshold(
    img: np.ndarray, threshold: float = 0.5, invert: bool = False, global_params={}
) -> np.ndarray:
    """Apply threshold effect"""
    # Convert to grayscale
    gray = img.mean(axis=2)
    # Apply threshold
    binary = (gray > threshold).astype(np.float32)
    if invert:
        binary = 1.0 - binary
    # Convert back to RGB
    binary_rgb = np.stack([binary] * 3, axis=2)
    
    title = f"Threshold: {threshold:.2f}, Invert: {'ON' if invert else 'OFF'}"
    global_params["__output_styles"]["thresholded"] = {"title": title}
    return binary_rgb


@interactive(
    rotation=CircularControl(0.0, [0.0, 360.0], modulo=True),  # CircularControl (float)
    scale=(1.0, [0.5, 2.0]),  # Float slider
)
def apply_transform(
    img: np.ndarray, rotation: float = 0.0, scale: float = 1.0, global_params={}
) -> np.ndarray:
    """Apply rotation and scale (simplified - just shows the concept)"""
    # For demo purposes, we'll just apply scale visually
    # Full rotation would require more complex image processing
    h, w = img.shape[:2]
    new_h, new_w = int(h * scale), int(w * scale)
    
    if scale != 1.0:
        try:
            import cv2
            transformed = cv2.resize(img, (new_w, new_h))
            # Center crop or pad to original size
            if scale > 1.0:
                # Crop center
                start_y = (new_h - h) // 2
                start_x = (new_w - w) // 2
                transformed = transformed[start_y : start_y + h, start_x : start_x + w]
            else:
                # Pad center
                pad_y = (h - new_h) // 2
                pad_x = (w - new_w) // 2
                transformed = np.pad(
                    transformed,
                    ((pad_y, h - new_h - pad_y), (pad_x, w - new_w - pad_x), (0, 0)),
                    mode="constant",
                    constant_values=0.5,
                )
        except ImportError:
            # Fallback: just return original if cv2 not available
            transformed = img.copy()
    else:
        transformed = img.copy()
    
    title = f"Rotation: {rotation:.0f}°, Scale: {scale:.2f}"
    global_params["__output_styles"]["transformed"] = {"title": title}
    return transformed


@interactive(
    color_mode=Control("rgb", ["rgb", "grayscale", "sepia", "negative"]),  # String dropdown
    intensity=(1.0, [0.0, 1.0]),  # Float slider
)
def apply_color_effect(
    img: np.ndarray, color_mode: str = "rgb", intensity: float = 1.0, global_params={}
) -> np.ndarray:
    """Apply various color effects"""
    result = img.copy()
    
    if color_mode == "grayscale":
        gray = img.mean(axis=2, keepdims=True)
        result = result * (1 - intensity) + gray * intensity
    elif color_mode == "sepia":
        sepia_filter = np.array([[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]])
        sepia_img = img @ sepia_filter.T
        result = result * (1 - intensity) + sepia_img * intensity
        result = np.clip(result, 0, 1)
    elif color_mode == "negative":
        negative = 1.0 - img
        result = result * (1 - intensity) + negative * intensity
    
    title = f"Color: {color_mode}, Intensity: {intensity:.2f}"
    global_params["__output_styles"]["colored"] = {"title": title}
    return result


@interactive(
    custom_text=TextPrompt("Widget Showcase"),  # TextPrompt
    text_size=(50, [20, 100]),  # Int slider
)
def add_text_overlay(
    img: np.ndarray, custom_text: str = "Widget Showcase", text_size: int = 50, global_params={}
) -> np.ndarray:
    """Add text overlay (simplified - just shows the concept)"""
    # For demo purposes, we'll create a simple overlay
    # In a real implementation, you'd use PIL or OpenCV to draw text
    result = img.copy()
    h, w = img.shape[:2]
    
    # Create a semi-transparent overlay at the bottom
    overlay_height = min(60, h // 10)
    overlay = result[-overlay_height:, :].copy()
    overlay = overlay * 0.7 + 0.3  # Darken slightly
    result[-overlay_height:, :] = overlay
    
    title = f"Text: '{custom_text}' (size: {text_size})"
    global_params["__output_styles"]["text_overlay"] = {"title": title}
    return result


@interactive(
    noise_amount=KeyboardControl(0.1, [0.0, 0.5], keydown="down", keyup="up", modulo=False),  # KeyboardControl - default 0.1
    enable_noise=(True,),  # Bool checkbox - enabled by default
)
def add_noise(
    img: np.ndarray, noise_amount: float = 0.0, enable_noise: bool = False, global_params={}
) -> np.ndarray:
    """Add noise effect (controlled by keyboard)"""
    if not enable_noise:
        global_params["__output_styles"]["noisy"] = {"title": "Noise: OFF"}
        return img
    
    noise = np.random.normal(0, noise_amount, img.shape)
    noisy_img = np.clip(img + noise, 0.0, 1.0)
    
    title = f"Noise: ON (amount: {noise_amount:.3f}, use ↑↓ keys)"
    global_params["__output_styles"]["noisy"] = {"title": title}
    return noisy_img


# ============================================================================
# Pipeline function - demonstrates multi-image layouts
# NOTE: Pipeline functions can ONLY contain function calls, no if/else statements!
# ============================================================================


def widgets_showcase_pipeline(img_list: List[Path]):
    """Main pipeline showcasing all widgets and multi-image layouts
    
    Pipeline functions must contain ONLY function calls - no control flow (if/else/for).
    The AST parser analyzes the function to build the execution graph.
    
    Layout is controlled via global_params["layout_mode"] string and set_layout_outputs().
    """
    # Process images through various filters
    original = select_image(img_list)
    adjusted = adjust_brightness_contrast(original)
    blurred = apply_blur(adjusted)
    thresholded = apply_threshold(blurred)
    transformed = apply_transform(original)
    colored = apply_color_effect(original)
    text_overlay = add_text_overlay(original)
    noisy = add_noise(original)
    
    # Set layout outputs based on layout_mode in global_params
    # This modifies pipeline.outputs to control the grid arrangement
    set_layout_outputs()
    
    # Return all images - the actual layout is controlled by pipeline.outputs
    # which is set by set_layout_outputs() based on layout_mode string
    return [
        original,
        adjusted,
        blurred,
        thresholded,
        transformed,
        colored,
        text_overlay,
        noisy,
    ]


# ============================================================================
# Main demo function
# ============================================================================


def main_demo(img_list: List[Path], backend="qt"):
    """Run the widgets showcase demo"""
    pipe = HeadlessPipeline.from_function(widgets_showcase_pipeline, cache=False)
    
    # Only import Kivy if it's actually needed
    global InteractivePipeKivy
    if backend == "kivy":
        import os
        os.environ["KIVY_NO_ARGS"] = "1"
        try:
            from interactive_pipe.graphical.kivy_gui import InteractivePipeKivy
            BACKEND_OPTIONS.append("kivy")
        except ImportError:
            raise ImportError("Kivy backend requested but Kivy is not available")
    
    assert backend in BACKEND_OPTIONS, f"Backend '{backend}' not available. Available: {BACKEND_OPTIONS}"
    
    backend_pipeline = {
        "qt": InteractivePipeQT,
        "mpl": InteractivePipeMatplotlib,
        "nb": InteractivePipeJupyter,
        "gradio": InteractivePipeGradio,
    }
    if InteractivePipeKivy is not None:
        backend_pipeline["kivy"] = InteractivePipeKivy
    
    app = backend_pipeline[backend](
        pipeline=pipe,
        name="Widgets Showcase Demo",
        size=(10, 10) if backend == "nb" else None,
    )
    app(img_list)


if __name__ == "__main__":
    img_list = get_image_paths()
    parser = argparse.ArgumentParser(
        description="Widgets showcase demo - demonstrates all widget types and multi-image layouts"
    )
    backend_choices = BACKEND_OPTIONS + ["kivy"]
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=backend_choices,
        default=BACKEND_OPTIONS[0],
        help=f"Backend to use: {', '.join(backend_choices)} (default: {BACKEND_OPTIONS[0]})",
    )
    args = parser.parse_args()
    main_demo(img_list, backend=args.backend)
