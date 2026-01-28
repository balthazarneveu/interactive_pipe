"""
Demo showcasing control grouping feature.

This demo demonstrates how to organize related controls into collapsible groups
using the `group` parameter. Groups help organize complex UIs with many controls.

Features demonstrated:
- Controls grouped by category (Text Settings, Colors, Effects)
- Ungrouped controls (for comparison)
- Mix of different control types within groups
- Abbreviated tuple syntax with group parameter
"""

import argparse
from pathlib import Path

import numpy as np

from interactive_pipe import (
    TextPrompt,
    interactive,
    interactive_pipeline,
    layout,
)
from interactive_pipe.data_objects.image import Image


def get_image_path():
    """Get a sample image path"""
    img_folder = Path(__file__).parent / "images"
    img_list = sorted(list(img_folder.glob("*.png")))
    if img_list:
        return img_list[0]
    # Fallback: create a simple test image
    return None


# ============================================================================
# Filters with grouped controls
# ============================================================================


@interactive()
def load_image(img_path: Path) -> np.ndarray:
    """Load the input image"""
    if img_path is None or not img_path.exists():
        # Create a simple gradient test image
        img = np.zeros((200, 300, 3), dtype=np.float32)
        for i in range(200):
            img[i, :, 0] = i / 200.0  # Red gradient
            img[i, :, 1] = 0.5  # Constant green
            img[i, :, 2] = 1.0 - i / 200.0  # Blue inverse gradient
        layout.style("original", title="Test Image (Generated)")
        return img
    else:
        img = Image.load_image(str(img_path))
        layout.style("original", title=f"Original: {img_path.stem}")
        return img


@interactive(
    # Text Settings group
    custom_text=TextPrompt("Hello World!", group="Text Settings"),
    text_size=(50, [20, 100], "Font Size", "Text Settings"),
    text_bold=(False, "Bold", "Text Settings"),
    text_italic=(False, "Italic", "Text Settings"),
    # Color Adjustments group
    brightness=(0.0, [-1.0, 1.0], "Brightness", "Color Adjustments"),
    contrast=(0.0, [-1.0, 1.0], "Contrast", "Color Adjustments"),
    saturation=(1.0, [0.0, 2.0], "Saturation", "Color Adjustments"),
    # Effects group
    blur_amount=(0, [0, 10], "Blur Radius", "Effects"),
    sharpen=(0.0, [0.0, 2.0], "Sharpen", "Effects"),
    vignette=(0.0, [0.0, 1.0], "Vignette", "Effects"),
    # Ungrouped controls (for comparison)
    enable_processing=(True, "Enable All Processing"),
    output_quality=(
        "high",
        ["low", "medium", "high", "ultra"],
        "Output Quality",
    ),
)
def process_image(
    img: np.ndarray,
    custom_text: str = "Hello World!",
    text_size: int = 50,
    text_bold: bool = False,
    text_italic: bool = False,
    brightness: float = 0.0,
    contrast: float = 0.0,
    saturation: float = 1.0,
    blur_amount: int = 0,
    sharpen: float = 0.0,
    vignette: float = 0.0,
    enable_processing: bool = True,
    output_quality: str = "high",
) -> np.ndarray:
    """Apply various effects with grouped controls"""

    if not enable_processing:
        layout.style("processed", title="Processing Disabled", subtitle="Toggle to enable")
        return img

    result = img.copy()

    # === Color Adjustments Group ===
    # Apply brightness
    if brightness != 0.0:
        result = result + brightness

    # Apply contrast
    if contrast != 0.0:
        result = (result - 0.5) * (1.0 + contrast) + 0.5

    # Apply saturation (convert to grayscale for saturation control)
    if saturation != 1.0:
        gray = result.mean(axis=2, keepdims=True)
        result = gray + (result - gray) * saturation

    result = np.clip(result, 0.0, 1.0)

    # === Effects Group ===
    # Apply blur
    if blur_amount > 0:
        h, w, c = result.shape
        blurred = result.copy()
        for y in range(h):
            for x in range(w):
                x_start = max(0, x - blur_amount)
                x_end = min(w, x + blur_amount + 1)
                blurred[y, x] = result[y, x_start:x_end].mean(axis=0)
        result = blurred

    # Apply sharpen (simple unsharp mask)
    if sharpen > 0.0:
        # Simple sharpening by subtracting a blurred version
        h, w, c = result.shape
        blurred = result.copy()
        blur_r = 1
        for y in range(h):
            for x in range(w):
                x_start = max(0, x - blur_r)
                x_end = min(w, x + blur_r + 1)
                blurred[y, x] = result[y, x_start:x_end].mean(axis=0)
        result = result + sharpen * (result - blurred)
        result = np.clip(result, 0.0, 1.0)

    # Apply vignette
    if vignette > 0.0:
        h, w = result.shape[:2]
        y, x = np.ogrid[:h, :w]
        cx, cy = w / 2, h / 2
        # Distance from center, normalized
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        dist = dist / dist.max()
        # Create vignette mask
        mask = 1.0 - vignette * dist
        mask = np.clip(mask, 0, 1)
        result = result * mask[:, :, np.newaxis]

    # === Text Settings Group ===
    # Text overlay info (not actually drawing text, just showing it's being processed)
    text_info = f"Text: '{custom_text}' (size={text_size}"
    if text_bold:
        text_info += ", bold"
    if text_italic:
        text_info += ", italic"
    text_info += ")"

    # Build title with active effects
    active_effects = []
    if brightness != 0.0:
        active_effects.append(f"bright={brightness:+.1f}")
    if contrast != 0.0:
        active_effects.append(f"cont={contrast:+.1f}")
    if saturation != 1.0:
        active_effects.append(f"sat={saturation:.1f}")
    if blur_amount > 0:
        active_effects.append(f"blur={blur_amount}")
    if sharpen > 0.0:
        active_effects.append(f"sharp={sharpen:.1f}")
    if vignette > 0.0:
        active_effects.append(f"vign={vignette:.1f}")

    title = "Processed"
    if active_effects:
        title += f" [{', '.join(active_effects)}]"

    subtitle = f"{text_info} | Quality: {output_quality}"
    layout.style("processed", title=title, subtitle=subtitle)

    return result


# ============================================================================
# Pipeline
# ============================================================================


def grouped_controls_pipeline(img_path: Path):
    """Main pipeline demonstrating grouped controls"""
    original = load_image(img_path)
    processed = process_image(original)
    return [original, processed]


if __name__ == "__main__":
    img_path = get_image_path()

    parser = argparse.ArgumentParser(description="Grouped controls demo - organize controls into collapsible groups")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("GROUPED CONTROLS DEMO")
    print("=" * 60)
    print("\nThis demo showcases the control grouping feature.")
    print("\nControls are organized into groups:")
    print("  - Text Settings (text options)")
    print("  - Color Adjustments (brightness, contrast, saturation)")
    print("  - Effects (blur, sharpen, vignette)")
    print("\nUngrouped controls appear separately:")
    print("  - Enable All Processing (checkbox)")
    print("  - Output Quality (dropdown)")
    print("\nNote: Qt backend supports QGroupBox rendering.")
    print("=" * 60 + "\n")

    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Grouped Controls Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(grouped_controls_pipeline)(img_path)
