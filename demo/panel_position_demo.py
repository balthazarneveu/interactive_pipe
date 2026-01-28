"""
Demo showcasing Panel positioning feature (left, right, top, bottom).

This demo demonstrates:
- Panels positioned on the left side of images
- Panels positioned on the right side of images
- Panels positioned on top of images
- Panels positioned below images (default)
- Mix of different positions simultaneously
- Backward compatibility (panels without position default to bottom)
"""

import argparse
from pathlib import Path

import numpy as np

from interactive_pipe import (
    Panel,
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
    return None


# ============================================================================
# Define Panel structure with positions
# ============================================================================

# Panels positioned on different sides
tools_panel = Panel("Tools", position="left", collapsible=True)
settings_panel = Panel("Settings", position="right", collapsible=True)
info_panel = Panel("Info", position="top", collapsible=True)
color_panel = Panel("Color Adjustments", position="bottom")  # Explicit bottom
effects_panel = Panel("Effects", position="bottom")  # Default position (None = bottom)


# ============================================================================
# Filters using Panel positioning
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
    # Tools panel (left)
    crop_x: int = 0,
    crop_y: int = 0,
    crop_width: int = 100,
    crop_height: int = 100,
    rotate: float = 0.0,
    # Settings panel (right)
    enable_gamma: bool = True,
    gamma: float = 1.0,
    enable_noise: bool = False,
    noise_amount: float = 0.0,
    # Info panel (top)
    show_info: bool = True,
    info_text: str = "Panel Position Demo",
    # Color panel (bottom)
    brightness: float = 0.0,
    contrast: float = 0.0,
    saturation: float = 1.0,
    # Effects panel (bottom)
    blur_amount: int = 0,
    sharpen: float = 0.0,
) -> np.ndarray:
    """Apply various effects with panels positioned on different sides"""

    result = img.copy()
    h, w = result.shape[:2]

    # === Tools Panel (left) ===
    # Crop
    if crop_width > 0 and crop_height > 0:
        x1 = max(0, min(crop_x, w - 1))
        y1 = max(0, min(crop_y, h - 1))
        x2 = max(x1 + 1, min(crop_x + crop_width, w))
        y2 = max(y1 + 1, min(crop_y + crop_height, h))
        result = result[y1:y2, x1:x2]
        h, w = result.shape[:2]

    # Rotate (simple 90-degree rotations for demo)
    if abs(rotate) > 0.25:
        if rotate > 0.5:
            result = np.rot90(result, k=1)
        elif rotate < -0.5:
            result = np.rot90(result, k=3)
        h, w = result.shape[:2]

    # === Settings Panel (right) ===
    if enable_gamma and gamma != 1.0:
        result = np.power(result, 1.0 / gamma)
        result = np.clip(result, 0.0, 1.0)

    if enable_noise and noise_amount > 0.0:
        noise = np.random.normal(0, noise_amount, result.shape).astype(np.float32)
        result = result + noise
        result = np.clip(result, 0.0, 1.0)

    # === Color Panel (bottom) ===
    if brightness != 0.0:
        result = result + brightness

    if contrast != 0.0:
        result = (result - 0.5) * (1.0 + contrast) + 0.5

    if saturation != 1.0:
        gray = result.mean(axis=2, keepdims=True)
        result = gray + (result - gray) * saturation

    result = np.clip(result, 0.0, 1.0)

    # === Effects Panel (bottom) ===
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

    title = "Processed"
    if active_effects:
        title += f" [{', '.join(active_effects)}]"

    subtitle = ""
    if show_info:
        subtitle = info_text
    if enable_gamma:
        subtitle += f" | Gamma: {gamma:.2f}"
    if enable_noise:
        subtitle += f" | Noise: {noise_amount:.2f}"

    layout.style("processed", title=title, subtitle=subtitle)

    return result


# ============================================================================
# Pipeline
# ============================================================================


def panel_position_demo_pipeline(img_path: Path):
    """Main pipeline demonstrating panel positioning"""
    original = load_image(img_path)
    processed = process_image(original)
    return [original, processed]


if __name__ == "__main__":
    img_path = get_image_path()

    parser = argparse.ArgumentParser(description="Panel positioning demo - panels on left, right, top, and bottom")
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
    print("PANEL POSITIONING DEMO")
    print("=" * 70)
    print("\nThis demo showcases panels positioned on different sides:")
    print("  - Tools Panel: LEFT side (collapsible)")
    print("  - Settings Panel: RIGHT side (collapsible)")
    print("  - Info Panel: TOP (collapsible)")
    print("  - Color Panel: BOTTOM (default position)")
    print("  - Effects Panel: BOTTOM (default position)")
    print("\nNote: Panels without position parameter default to 'bottom'")
    print("=" * 70 + "\n")

    interactive(
        # Tools panel (left)
        crop_x=(0, [0, 300], "Crop X", tools_panel),
        crop_y=(0, [0, 200], "Crop Y", tools_panel),
        crop_width=(100, [10, 300], "Crop Width", tools_panel),
        crop_height=(100, [10, 200], "Crop Height", tools_panel),
        rotate=(0.0, [-1.0, 1.0], "Rotate", tools_panel),
        # Settings panel (right)
        enable_gamma=(True, "Enable Gamma", settings_panel),
        gamma=(1.0, [0.1, 3.0], "Gamma", settings_panel),
        enable_noise=(False, "Enable Noise", settings_panel),
        noise_amount=(0.0, [0.0, 0.2], "Noise Amount", settings_panel),
        # Info panel (top)
        show_info=(True, "Show Info", info_panel),
        info_text=TextPrompt("Panel Position Demo", name="Info Text", group=info_panel),
        # Color panel (bottom)
        brightness=(0.0, [-1.0, 1.0], "Brightness", color_panel),
        contrast=(0.0, [-1.0, 1.0], "Contrast", color_panel),
        saturation=(1.0, [0.0, 2.0], "Saturation", color_panel),
        # Effects panel (bottom)
        blur_amount=(0, [0, 10], "Blur Radius", effects_panel),
        sharpen=(0.0, [0.0, 2.0], "Sharpen", effects_panel),
    )(process_image)
    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Panel Position Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(panel_position_demo_pipeline)(img_path)
