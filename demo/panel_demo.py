"""
Demo showcasing the Panel system for organizing controls.

This demo demonstrates:
- Simple panels (backward compatible with string-based groups)
- Nested panel hierarchies
- Grid layouts with panels side-by-side
- Collapsible panels
- Mix of Panel objects and string-based groups
- Ungrouped controls
"""

import numpy as np
from pathlib import Path
import argparse
from interactive_pipe import (
    interactive,
    interactive_pipeline,
    Panel,
    TextPrompt,
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
# Define Panel structure
# ============================================================================

# Create individual panels
text_panel = Panel("Text Settings", collapsible=True)
color_panel = Panel("Color Adjustments", collapsible=True)
effects_panel = Panel("Effects", collapsible=True, collapsed=False)

# Create nested panel structure with grid layout
main_panel = Panel("Processing Controls").add_elements(
    [
        [text_panel, color_panel],  # Row 1: Text and Color side by side
        [effects_panel],  # Row 2: Effects panel full width
    ]
)


# ============================================================================
# Filters using Panel system
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
    custom_text: str = "Panel Demo!",
    text_size: int = 50,
    text_bold: bool = False,
    text_italic: bool = False,
    brightness: float = 0.0,
    contrast: float = 0.0,
    saturation: float = 1.0,
    hue_shift: float = 0.0,
    blur_amount: int = 0,
    sharpen: float = 0.0,
    vignette: float = 0.0,
    enable_processing: bool = True,
    output_quality: str = "high",
) -> np.ndarray:
    """Apply various effects with nested panel organization"""

    if not enable_processing:
        layout.style(
            "processed", title="Processing Disabled", subtitle="Toggle to enable"
        )
        return img

    result = img.copy()

    # === Color Adjustments Panel ===
    if brightness != 0.0:
        result = result + brightness

    if contrast != 0.0:
        result = (result - 0.5) * (1.0 + contrast) + 0.5

    if saturation != 1.0:
        gray = result.mean(axis=2, keepdims=True)
        result = gray + (result - gray) * saturation

    if hue_shift != 0.0:
        # Simple hue shift (just rotate channels for demo)
        shift_amount = int(hue_shift * 10) % 3
        if shift_amount != 0:
            result = np.roll(result, shift_amount, axis=2)

    result = np.clip(result, 0.0, 1.0)

    # === Effects Panel ===
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

    if vignette > 0.0:
        h, w = result.shape[:2]
        y, x = np.ogrid[:h, :w]
        cx, cy = w / 2, h / 2
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        dist = dist / dist.max()
        mask = 1.0 - vignette * dist
        mask = np.clip(mask, 0, 1)
        result = result * mask[:, :, np.newaxis]

    # Build title with active effects
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
    if vignette > 0.0:
        active_effects.append(f"vign={vignette:.1f}")

    # Text info
    text_info = f"Text: '{custom_text}' (size={text_size}"
    if text_bold:
        text_info += ", bold"
    if text_italic:
        text_info += ", italic"
    text_info += ")"

    title = "Processed"
    if active_effects:
        title += f" [{', '.join(active_effects)}]"

    subtitle = f"{text_info} | Quality: {output_quality}"
    layout.style("processed", title=title, subtitle=subtitle)

    return result


# Demo using simple string-based groups (backward compatibility)
@interactive(
    # String groups still work!
    gain=(1.0, [0.0, 3.0], "Gain", "Simple Group"),
    offset=(0.0, [-1.0, 1.0], "Offset", "Simple Group"),
)
def adjust_simple(
    img: np.ndarray,
    gain: float = 1.0,
    offset: float = 0.0,
) -> np.ndarray:
    """Simple adjustments using string-based groups"""
    result = img * gain + offset
    result = np.clip(result, 0.0, 1.0)
    layout.style(
        "simple",
        title="Simple Adjustments",
        subtitle=f"gain={gain:.1f}, offset={offset:+.1f}",
    )
    return result


# ============================================================================
# Pipeline
# ============================================================================


def panel_demo_pipeline(img_path: Path):
    """Main pipeline demonstrating nested panels and grid layouts"""
    original = load_image(img_path)
    processed = process_image(original)
    simple = adjust_simple(original)
    return [original, processed, simple]


if __name__ == "__main__":
    img_path = get_image_path()

    parser = argparse.ArgumentParser(
        description="Panel system demo - organize controls into nested, collapsible groups"
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
    print("PANEL SYSTEM DEMO")
    print("=" * 70)
    print("\nThis demo showcases the new Panel system for organizing controls.")
    print("\nPanel Hierarchy:")
    print("  Main Panel 'Processing Controls'")
    print("    ├─ Row 1 (grid):")
    print("    │   ├─ Text Settings (collapsible)")
    print("    │   └─ Color Adjustments (collapsible)")
    print("    └─ Row 2:")
    print("        └─ Effects (collapsible, starts collapsed)")
    print("\nAdditional Features:")
    print("  - Simple Group: Uses string-based groups (backward compatible)")
    print("  - Ungrouped controls appear separately")
    print("\nQt backend features:")
    print("  - Nested QGroupBox widgets")
    print("  - Grid layouts for side-by-side panels")
    print("  - Collapsible panels (click checkbox to collapse/expand)")
    print("=" * 70 + "\n")
    interactive(
        # Text Settings Panel - using Panel object
        custom_text=TextPrompt("Panel Demo!", group=text_panel),
        text_size=(50, [20, 100], "Font Size", text_panel),
        text_bold=(False, "Bold", text_panel),
        text_italic=(False, "Italic", text_panel),
        # Color Adjustments Panel - using Panel object
        brightness=(0.0, [-1.0, 1.0], "Brightness", color_panel),
        contrast=(0.0, [-1.0, 1.0], "Contrast", color_panel),
        saturation=(1.0, [0.0, 2.0], "Saturation", color_panel),
        hue_shift=(0.0, [-0.5, 0.5], "Hue Shift", color_panel),
        # Effects Panel - using Panel object
        blur_amount=(0, [0, 10], "Blur Radius", effects_panel),
        sharpen=(0.0, [0.0, 2.0], "Sharpen", effects_panel),
        vignette=(0.0, [0.0, 1.0], "Vignette", effects_panel),
        # Ungrouped controls (for comparison)
        enable_processing=(True, "Enable All Processing"),
        output_quality=(
            "high",
            ["low", "medium", "high", "ultra"],
            "Output Quality",
        ),
    )(process_image)
    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Panel System Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(panel_demo_pipeline)(img_path)
