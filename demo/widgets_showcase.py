"""
Comprehensive demo showcasing all widget types, controls, and multi-image layouts.

This demo demonstrates:
- Float sliders (with range)
- Int sliders (with range)
- Bool checkboxes
- String dropdowns
- TextPrompt (text input)
- CircularControl (circular slider)
- RangeControl (two-handle min/max slider)
- KeyboardControl (keyboard shortcuts)
- Multi-image layouts (1x3, 2x2, 3x1, etc.)
"""

import argparse
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from interactive_pipe import (
    CircularControl,
    Control,
    Image,
    KeyboardControl,
    RangeControl,
    TextPrompt,
    context,
    interactive,
    interactive_pipeline,
    layout,
)


def get_image_paths(img_folder: Path = Path(__file__).parent / "images"):
    """Get list of image paths"""
    img_list = sorted(list(img_folder.glob("*.png")))
    return img_list


# ============================================================================
# Interactive Filters - showcasing different widget types
# ============================================================================


@interactive(
    image_index=(0, [0, 3]),  # Int slider with range
    layout_mode=Control(
        "last_output", ["row_1x4", "grid_2x2", "column_3x1", "grid_2x4", "last_output"]
    ),  # String dropdown
)
def select_image(
    img_list: List[Path],
    image_index: int = 0,
    layout_mode: str = "last_output",
) -> np.ndarray:
    """Select an image from the list"""
    idx = min(image_index, len(img_list) - 1)
    img = Image.load_image(str(img_list[idx]))
    title = f"Original {idx + 1}/{len(img_list)}: {img_list[idx].stem}"

    layout.style("original", title=title)
    # Attribute-style access
    context.layout_mode = layout_mode

    return img


def set_layout_outputs():
    """Set pipeline.outputs based on layout_mode string in context.

    This function modifies pipeline.outputs to control the image layout arrangement.
    The layout_mode string determines how images are arranged in the grid.

    The outputs use variable names (strings) matching the return statement variable names.
    """
    layout_mode = context.get("layout_mode", "last_output")

    # Define output layouts as 2D structures of variable names (strings)
    # Variable names must match the return statement variable names
    layouts = {
        "row_1x4": [["original", "adjusted", "blurred", "thresholded"]],
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
        "last_output": [["noisy"]],  # Show only the last output (noisy)
    }

    if layout_mode in layouts:
        layout.grid(layouts[layout_mode])


@interactive(
    brightness=(0.0, [-1.0, 1.0]),  # Float slider: -1 (dark) to +1 (bright)
    contrast=(0.0, [-1.0, 1.0]),  # Float slider: -1 (low) to +1 (high)
    levels=RangeControl((0.0, 1.0), [0.0, 1.0], name="input levels"),  # Two-handle (lo, hi) slider
)
def adjust_brightness_contrast(
    img: np.ndarray, brightness: float = 0.0, contrast: float = 0.0, levels=(0.0, 1.0)
) -> np.ndarray:
    """Adjust input levels, brightness and contrast"""
    # Input levels: stretch [lo, hi] to [0, 1] (the filter receives a (lo, hi) tuple)
    lo, hi = levels
    img = np.clip((img - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
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

    title = f"Levels: [{lo:.2f}, {hi:.2f}], Brightness: {brightness:+.2f}, Contrast: {contrast:+.2f}"
    layout.style("adjusted", title=title)
    return contrasted_img


def _box_blur_axis(img: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Box blur of the given radius along one axis, averaging only over valid (in-image) pixels."""
    radius = int(radius)
    n = img.shape[axis]
    csum = np.cumsum(img, axis=axis, dtype=np.float64)
    zero_shape = list(img.shape)
    zero_shape[axis] = 1
    csum = np.concatenate([np.zeros(zero_shape), csum], axis=axis)  # csum[k] = sum of first k samples
    idx = np.arange(n)
    hi = np.minimum(idx + radius + 1, n)
    lo = np.maximum(idx - radius, 0)
    window_sum = np.take(csum, hi, axis=axis) - np.take(csum, lo, axis=axis)
    count_shape = [1] * img.ndim
    count_shape[axis] = n
    counts = (hi - lo).reshape(count_shape)
    return (window_sum / counts).astype(img.dtype)


@interactive(
    blur_amount=CircularControl(3, [1, 15], modulo=True),  # CircularControl (int)
    enable_blur=(False,),  # Bool checkbox
)
def apply_blur(img: np.ndarray, blur_amount: int = 3, enable_blur: bool = False) -> np.ndarray:
    """Apply blur effect"""
    if not enable_blur:
        layout.style("blurred", title="Blur: OFF")
        return img

    # Separable box blur (vectorized): horizontal pass then vertical pass
    blurred = _box_blur_axis(_box_blur_axis(img, blur_amount, axis=1), blur_amount, axis=0)

    title = f"Blur: ON (radius={blur_amount})"
    layout.style("blurred", title=title)
    return blurred


@interactive(
    threshold=(0.5, [0.0, 1.0]),  # Float slider
    invert=(False,),  # Bool checkbox
)
def apply_threshold(img: np.ndarray, threshold: float = 0.5, invert: bool = False) -> np.ndarray:
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
    layout.style("thresholded", title=title)
    return binary_rgb


@interactive(
    rotation=CircularControl(0.0, [0.0, 360.0], modulo=True),  # CircularControl (float)
    scale=(1.0, [0.5, 2.0]),  # Float slider
)
def apply_transform(img: np.ndarray, rotation: float = 0.0, scale: float = 1.0) -> np.ndarray:
    """Rotate (around the center) and zoom the image, keeping the original size"""
    h, w = img.shape[:2]
    pil = PILImage.fromarray((np.clip(img, 0.0, 1.0) * 255).astype(np.uint8))
    # Zoom: resize then center crop (scale>1) or pad with mid-gray (scale<1)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    pil = pil.resize((new_w, new_h), PILImage.BILINEAR)
    canvas = PILImage.new("RGB", (w, h), (128, 128, 128))
    canvas.paste(pil, ((w - new_w) // 2, (h - new_h) // 2))
    canvas = canvas.rotate(rotation, resample=PILImage.BILINEAR, fillcolor=(128, 128, 128))
    transformed = np.asarray(canvas).astype(np.float32) / 255.0

    title = f"Rotation: {rotation:.0f}°, Scale: {scale:.2f}"
    layout.style("transformed", title=title)
    return transformed


@interactive(
    color_mode=Control("rgb", ["rgb", "grayscale", "sepia", "negative"]),  # String dropdown
    intensity=(1.0, [0.0, 1.0]),  # Float slider
)
def apply_color_effect(img: np.ndarray, color_mode: str = "rgb", intensity: float = 1.0) -> np.ndarray:
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
    layout.style("colored", title=title)
    return result


@interactive(
    custom_text=TextPrompt("Widget Showcase"),  # TextPrompt
    text_size=(50, [20, 100]),  # Int slider
)
def add_text_overlay(
    img: np.ndarray,
    custom_text: str = "Widget Showcase",
    text_size: int = 50,
) -> np.ndarray:
    """Draw the custom text at the bottom of the image"""
    h, w = img.shape[:2]
    pil = PILImage.fromarray((np.clip(img, 0.0, 1.0) * 255).astype(np.uint8))
    draw = ImageDraw.Draw(pil)
    try:
        font = ImageFont.load_default(size=int(text_size))
    except TypeError:  # old Pillow: fixed-size default font
        font = ImageFont.load_default()
    draw.text(
        (w // 2, h - 10),
        custom_text,
        font=font,
        anchor="mb",
        fill=(255, 255, 255),
        stroke_width=max(1, int(text_size) // 15),
        stroke_fill=(0, 0, 0),
    )
    result = np.asarray(pil).astype(np.float32) / 255.0

    title = f"Text: '{custom_text}' (size: {text_size})"
    layout.style("text_overlay", title=title)
    return result


@interactive(
    noise_amount=KeyboardControl(
        0.1, [0.0, 0.5], keydown="down", keyup="up", modulo=False
    ),  # KeyboardControl - default 0.1
    enable_noise=(True,),  # Bool checkbox - enabled by default
)
def add_noise(
    img: np.ndarray,
    noise_amount: float = 0.1,
    enable_noise: bool = True,
) -> np.ndarray:
    """Add noise effect (controlled by keyboard)"""
    if not enable_noise:
        layout.style("noisy", title="Noise: OFF")
        return img

    noise = np.random.normal(0, noise_amount, img.shape)
    noisy_img = np.clip(img + noise, 0.0, 1.0)

    title = f"Noise: ON (amount: {noise_amount:.3f}, use ↑↓ keys)"
    layout.style("noisy", title=title)
    return noisy_img


# ============================================================================
# Pipeline function - demonstrates multi-image layouts
# NOTE: Pipeline functions can ONLY contain function calls, no if/else statements!
# ============================================================================


def widgets_showcase_pipeline(img_list: List[Path]):
    """Main pipeline showcasing all widgets and multi-image layouts

    Pipeline functions must contain ONLY function calls - no control flow (if/else/for).
    The AST parser analyzes the function to build the execution graph.

    Layout is controlled via context["layout_mode"] string and set_layout_outputs().
    """
    # Process images through various filters
    original = select_image(img_list)
    adjusted = adjust_brightness_contrast(original)
    blurred = apply_blur(adjusted)
    thresholded = apply_threshold(blurred)
    transformed = apply_transform(blurred)
    colored = apply_color_effect(transformed)
    text_overlay = add_text_overlay(colored)
    noisy = add_noise(text_overlay)

    # Set layout outputs based on layout_mode in context
    # This modifies pipeline.outputs to control the grid arrangement
    set_layout_outputs()

    # Return all images - the actual layout is controlled by pipeline.outputs
    # which is set by set_layout_outputs()
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


if __name__ == "__main__":
    img_list = get_image_paths()
    parser = argparse.ArgumentParser(
        description="Widgets showcase demo - demonstrates all widget types and multi-image layouts"
    )
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "dpg", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Widgets Showcase Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(widgets_showcase_pipeline)(img_list)
