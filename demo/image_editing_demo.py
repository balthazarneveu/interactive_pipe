import argparse

import cv2
import numpy as np

from interactive_pipe import (
    Control,
    Panel,
    TextPrompt,
    interactive,
    interactive_pipeline,
)


def apply_knobs(
    img: np.ndarray,
    black_point: float = 0.0,
    white_point: float = 1.0,
    gamma: float = 1.0,
    contrast: float = 1.0,
    brightness: float = 0.0,
    saturation: float = 1.0,
    hue: float = 0.0,
):
    """Apply various image adjustments: black/white point, gamma, contrast, brightness, saturation, and hue."""
    result = img.copy()

    # Apply black and white point (contrast stretching)
    # Map values from [black_point, white_point] to [0, 1]
    if black_point != 0.0 or white_point != 1.0:
        result = (result - black_point) / (white_point - black_point + 1e-10)
        result = np.clip(result, 0.0, 1.0)

    # Apply gamma correction
    # Map gamma slider [0, 1] to actual gamma [0.1, 2.0]
    # Default gamma=1.0 should map to actual_gamma=1.0 (no change)
    # Use piecewise: [0, 1.0) -> map normally, but handle 1.0 specially
    if gamma != 1.0:
        # Map [0, 1) to [0.1, 2.0] with 0.5 -> 1.0 as midpoint
        if gamma < 0.5:
            # [0, 0.5) -> [0.1, 1.0)
            actual_gamma = 0.1 + (gamma / 0.5) * 0.9
        elif gamma < 1.0:
            # [0.5, 1.0) -> [1.0, 2.0)
            actual_gamma = 1.0 + ((gamma - 0.5) / 0.5) * 1.0
        else:
            actual_gamma = 1.0  # gamma == 1.0 -> no change
        result = np.power(np.clip(result, 1e-10, 1.0), actual_gamma)

    # Apply contrast
    # Map contrast slider [0, 1] to actual contrast [0.1, 2.0]
    # Default contrast=1.0 should map to actual_contrast=1.0 (no change)
    if contrast != 1.0:
        if contrast < 0.5:
            actual_contrast = 0.1 + (contrast / 0.5) * 0.9  # [0, 0.5) -> [0.1, 1.0)
        elif contrast < 1.0:
            actual_contrast = 1.0 + ((contrast - 0.5) / 0.5) * 1.0  # [0.5, 1.0) -> [1.0, 2.0)
        else:
            actual_contrast = 1.0  # contrast == 1.0 -> no change
        result = (result - 0.5) * actual_contrast + 0.5

    # Apply brightness
    # Map brightness slider [0, 1] to actual brightness [0.0, 0.5]
    # Default brightness=0.0 (min) maps to actual_brightness=0.0 (no change)
    if brightness != 0.0:
        actual_brightness = brightness * 0.5  # [0, 1] -> [0.0, 0.5]
        result = result + actual_brightness

    # Apply saturation
    # saturation = 0: grayscale, saturation = 1: original, saturation > 1: more saturated
    if saturation != 1.0:
        gray = result.mean(axis=2, keepdims=True)
        result = gray + (result - gray) * saturation

    # Apply hue shift
    # Map hue from [0, 1] to RGB channel rotation (0-2 channels)
    if hue != 0.0:
        shift_amount = int(hue * 3) % 3
        if shift_amount != 0:
            result = np.roll(result, shift_amount, axis=2)

    # Clamp to valid range
    result = np.clip(result, 0.0, 1.0)
    return result


def create_colorful_chart(size=(512, 512)) -> np.ndarray:
    """Create a pretty colored synthetic chart with gradients and patterns."""
    h, w = size
    img = np.zeros((h, w, 3), dtype=np.float32)

    # Create coordinate grids
    y, x = np.ogrid[:h, :w]
    center_x, center_y = w // 2, h // 2

    # Create radial distance from center
    radius = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
    max_radius = np.sqrt(center_x**2 + center_y**2)
    normalized_radius = radius / max_radius

    # Create angle for color wheel effect
    angle = np.arctan2(y - center_y, x - center_x)
    normalized_angle = (angle + np.pi) / (2 * np.pi)  # [0, 1]

    # Create colorful radial gradient with hue variation
    # Red channel: varies with angle
    img[:, :, 0] = 0.5 + 0.5 * np.sin(normalized_angle * 2 * np.pi)
    # Green channel: varies with angle + offset
    img[:, :, 1] = 0.5 + 0.5 * np.sin(normalized_angle * 2 * np.pi + 2 * np.pi / 3)
    # Blue channel: varies with angle + offset
    img[:, :, 2] = 0.5 + 0.5 * np.sin(normalized_angle * 2 * np.pi + 4 * np.pi / 3)

    # Add radial brightness variation (darker at edges, brighter in center)
    radial_mask = 1.0 - normalized_radius * 0.3
    img = img * radial_mask[:, :, np.newaxis]

    # Add some checkerboard pattern overlay for texture
    checker_size = 32
    checker = ((x // checker_size) + (y // checker_size)) % 2
    checker_mask = 0.9 + 0.1 * checker
    img = img * checker_mask[:, :, np.newaxis]

    # Add some colorful bands
    band_freq = 8
    bands = 0.95 + 0.05 * np.sin(y * band_freq * 2 * np.pi / h)
    img = img * bands[:, :, np.newaxis]

    # Ensure values are in [0, 1]
    img = np.clip(img, 0.0, 1.0)

    return img


def add_text(img: np.ndarray, text: str = "nothing") -> np.ndarray:
    """Add text overlay to the image."""
    if text == "nothing" or not text:
        return img

    result = img.copy()
    h, w = img.shape[:2]

    # Convert to uint8 for cv2
    result_uint8 = (result * 255).astype(np.uint8)

    # Calculate text size based on image dimensions
    font_scale = min(w, h) / 400.0
    thickness = max(1, int(font_scale * 2))

    # Get text size to center it
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    # Position text at bottom center
    x = (w - text_width) // 2
    y = h - 20

    # Draw semi-transparent background rectangle
    overlay = result_uint8.copy()
    cv2.rectangle(
        overlay,
        (x - 10, y - text_height - 10),
        (x + text_width + 10, y + baseline + 10),
        (0, 0, 0),
        -1,
    )
    result_uint8 = cv2.addWeighted(result_uint8, 0.7, overlay, 0.3, 0)

    # Draw white text
    cv2.putText(
        result_uint8,
        text,
        (x, y),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )

    # Convert back to float [0, 1]
    result = result_uint8.astype(np.float32) / 255.0
    return result


def image_editing_pipeline(img: np.ndarray):  # pyright: ignore[reportUndefinedVariable]
    output = apply_knobs(img)
    output = add_text(output)
    return output


def add_interactivity():
    lighting_panel = Panel(
        "Lighting",
        collapsible=False,
        collapsed=False,
        detached=True,
        detached_size=(200, 200),
    )
    stretching_panel = Panel("Stretching", collapsible=True, collapsed=True)
    contrast_panel = Panel("Contrast", collapsible=True, collapsed=True)

    color_panel = Panel("Color", collapsible=True, collapsed=False)
    lighting_panel.add_elements([[contrast_panel, stretching_panel]])
    # main_panel = Panel("Image Editing", collapsible=True, collapsed=True)
    # main_panel.add_elements([[lighting_panel, color_panel]])
    interactive(
        black_point=Control(
            0.0,
            [0.0, 1.0],
            name="Black Point",
            group=contrast_panel,
            tooltip="Set the darkest point in the image. Values below this become black.",
        ),
        white_point=Control(
            1.0,
            [0.0, 1.0],
            name="White Point",
            group=contrast_panel,
            tooltip="Set the brightest point in the image. Values above this become white.",
        ),
        gamma=Control(
            1.0,
            [0.0, 1.0],
            name="Gamma",
            group=stretching_panel,
            tooltip="Adjust gamma correction. <0.5 darkens midtones, >0.5 brightens them.",
        ),
        contrast=Control(
            1.0,
            [0.0, 1.0],
            name="Contrast",
            group=stretching_panel,
            tooltip="Adjust image contrast. <0.5 reduces contrast, >0.5 increases it.",
        ),
        brightness=Control(
            0.0,
            [0.0, 1.0],
            name="Brightness",
            group=color_panel,
            tooltip="Adjust overall image brightness. Higher values make the image brighter.",
        ),
        saturation=Control(
            1.0,
            [0.0, 1.0],
            name="Saturation",
            group=color_panel,
            tooltip="Adjust color saturation. 0=grayscale, 1=original, >1=more vibrant.",
        ),
        hue=Control(
            0.0,
            [0.0, 1.0],
            name="Hue",
            group=color_panel,
            tooltip="Shift color hue by rotating RGB channels.",
        ),
    )(apply_knobs)
    interactive(
        text=TextPrompt(
            "Text",
            tooltip="Enter text to overlay on the image. Leave empty for no text.",
        ),
    )(add_text)


def launch(backend="qt"):
    add_interactivity()
    colorful_chart = create_colorful_chart(size=(512, 512))
    interactive_pipeline(
        gui=backend,
        cache=False,
        name="Image Editing",
    )(image_editing_pipeline)(colorful_chart)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Editing Demo")
    parser.add_argument(
        "-b",
        "--backend",
        choices=["qt", "gradio", "mpl", "notebook", "dpg"],
        default="qt",
        help="GUI backend to use: qt, gradio, mpl, notebook, or dpg (default: qt)",
    )
    args = parser.parse_args()
    launch(backend=args.backend)
