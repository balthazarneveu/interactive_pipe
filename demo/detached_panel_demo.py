"""
Demo showcasing detached panel windows in Qt backend.

This demo demonstrates:
- Detached panels that open in separate windows
- Regular panels in the main window
- Mixed panel types
"""

import numpy as np
from pathlib import Path
import argparse
from interactive_pipe import (
    interactive,
    interactive_pipeline,
    Panel,
    layout,
)
from interactive_pipe.data_objects.image import Image


def get_image_path():
    """Get a sample image path"""
    img_folder = Path(__file__).parent / "images"
    img_list = sorted(list(img_folder.glob("*.png")))
    if img_list:
        return img_list[0]
    return None


# ============================================================================
# Define Panel structure with detached panels
# ============================================================================

# Create a detached panel for color controls (opens in separate window)
color_panel = Panel(
    "Color Controls (Detached)",
    detached=True,
    detached_size=(350, 400),
    collapsible=True,
)

# Create a regular panel in main window
effects_panel = Panel("Effects", collapsible=True)

# Create another regular panel
output_panel = Panel("Output Settings")


# ============================================================================
# Filters
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


def process_image(
    img: np.ndarray,
    brightness: float = 0.0,
    contrast: float = 0.0,
    saturation: float = 1.0,
    hue_shift: float = 0.0,
    blur_amount: int = 0,
    sharpen: float = 0.0,
    enable_processing: bool = True,
    quality: str = "high",
) -> np.ndarray:
    """Apply various effects"""

    if not enable_processing:
        layout.style(
            "processed", title="Processing Disabled", subtitle="Toggle to enable"
        )
        return img

    result = img.copy()

    # === Color Adjustments (in detached window) ===
    if brightness != 0.0:
        result = result + brightness

    if contrast != 0.0:
        result = (result - 0.5) * (1.0 + contrast) + 0.5

    if saturation != 1.0:
        gray = result.mean(axis=2, keepdims=True)
        result = gray + (result - gray) * saturation

    if hue_shift != 0.0:
        shift_amount = int(hue_shift * 10) % 3
        if shift_amount != 0:
            result = np.roll(result, shift_amount, axis=2)

    result = np.clip(result, 0.0, 1.0)

    # === Effects (in main window) ===
    if blur_amount > 0:
        h, w, c = result.shape
        blurred = result.copy()
        for y in range(h):
            for x in range(w):
                x_start = max(0, x - blur_amount)
                x_end = min(w, x + blur_amount + 1)
                blurred[y, x] = result[y, x_start:x_end].mean(axis=0)
        result = blurred

    if sharpen > 0.0:
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

    # Build title
    active_effects = []
    if brightness != 0.0:
        active_effects.append(f"bright={brightness:+.1f}")
    if contrast != 0.0:
        active_effects.append(f"cont={contrast:+.1f}")
    if saturation != 1.0:
        active_effects.append(f"sat={saturation:.1f}")
    if hue_shift != 0.0:
        active_effects.append(f"hue={hue_shift:+.1f}")
    if blur_amount > 0:
        active_effects.append(f"blur={blur_amount}")
    if sharpen > 0.0:
        active_effects.append(f"sharp={sharpen:.1f}")

    title = "Processed"
    if active_effects:
        title += f" [{', '.join(active_effects)}]"

    subtitle = f"Quality: {quality}"
    layout.style("processed", title=title, subtitle=subtitle)

    return result


# ============================================================================
# Pipeline
# ============================================================================


def detached_panel_demo_pipeline(img_path: Path):
    """Main pipeline demonstrating detached panels"""
    original = load_image(img_path)
    processed = process_image(original)
    return [original, processed]


if __name__ == "__main__":
    img_path = get_image_path()

    parser = argparse.ArgumentParser(
        description="Detached panel demo - panels open in separate windows"
    )
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("DETACHED PANEL DEMO")
    print("=" * 70)
    print("\nThis demo showcases detached panels (Qt backend only).")
    print("\nPanel Configuration:")
    print("  - Color Controls: DETACHED (separate window)")
    print("  - Effects: Regular panel (main window)")
    print("  - Output Settings: Regular panel (main window)")
    print("\nThe detached panel should open in a separate window that can be")
    print("moved independently. Closing the main window will also close all")
    print("detached windows.")
    print("=" * 70 + "\n")

    interactive(
        # Color Controls Panel - DETACHED
        brightness=(0.0, [-1.0, 1.0], "Brightness", color_panel),
        contrast=(0.0, [-1.0, 1.0], "Contrast", color_panel),
        saturation=(1.0, [0.0, 2.0], "Saturation", color_panel),
        hue_shift=(0.0, [-0.5, 0.5], "Hue Shift", color_panel),
        # Effects Panel - in main window
        blur_amount=(0, [0, 10], "Blur Radius", effects_panel),
        sharpen=(0.0, [0.0, 2.0], "Sharpen", effects_panel),
        # Output Panel - in main window
        enable_processing=(True, "Enable Processing", output_panel),
        quality=(
            "high",
            ["low", "medium", "high", "ultra"],
            "Quality",
            output_panel,
        ),
    )(process_image)

    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Detached Panel Demo",
    )(
        detached_panel_demo_pipeline
    )(img_path)
