"""
Demo showcasing an image with two dependent curves: profile and histogram.

This demo demonstrates:
- Image generation with adjustable parameters
- Profile extraction (line section through the image)
- Histogram computation from image pixel values
- Multiple sliders controlling the image, which in turn affects the curves
"""

import argparse

import numpy as np

from interactive_pipe import Control, interactive, interactive_pipeline, layout
from interactive_pipe.data_objects.curves import Curve


@interactive(
    image_size=(400, [200, 800]),  # Int slider for image size
    pattern_frequency=(5.0, [1.0, 20.0]),  # Float slider for pattern frequency
    brightness=(0.5, [0.0, 1.0]),  # Float slider for brightness
    contrast=(1.0, [0.5, 2.0]),  # Float slider for contrast
    rotation=(0.0, [0.0, 360.0]),  # Float slider for rotation angle
)
def generate_image(
    image_size: int = 400,
    pattern_frequency: float = 5.0,
    brightness: float = 0.5,
    contrast: float = 1.0,
    rotation: float = 0.0,
) -> np.ndarray:
    """Generate a pattern image with adjustable parameters"""
    # Create coordinate grids
    y, x = np.mgrid[0:image_size, 0:image_size].astype(np.float32)

    # Center coordinates
    cx, cy = image_size / 2.0, image_size / 2.0

    # Rotate coordinates
    angle_rad = np.deg2rad(rotation)
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    x_rot = (x - cx) * cos_a - (y - cy) * sin_a + cx
    y_rot = (x - cx) * sin_a + (y - cy) * cos_a + cy

    # Create radial pattern
    r = np.sqrt((x_rot - cx) ** 2 + (y_rot - cy) ** 2)
    pattern = np.sin(pattern_frequency * r / (image_size / 10.0))

    # Create angular pattern
    angle = np.arctan2(y_rot - cy, x_rot - cx)
    angular_pattern = np.sin(pattern_frequency * angle)

    # Combine patterns
    combined = 0.5 * (pattern + angular_pattern)

    # Apply contrast and brightness
    combined = (combined - 0.5) * contrast + 0.5 + brightness - 0.5

    # Clamp to [0, 1] and convert to RGB
    combined = np.clip(combined, 0.0, 1.0)
    img = np.stack([combined] * 3, axis=2)

    title = f"Pattern: f={pattern_frequency:.1f}, B={brightness:.2f}, C={contrast:.2f}, R={rotation:.0f}°"
    layout.style("image", title=title)

    return img


@interactive(
    profile_line=(
        0.5,
        [0.0, 1.0],
    ),  # Float slider for profile line position (0=top, 1=bottom)
    profile_direction=Control("horizontal", ["horizontal", "vertical", "diagonal"]),  # Dropdown for direction
)
def extract_profile(
    img: np.ndarray,
    profile_line: float = 0.5,
    profile_direction: str = "horizontal",
) -> Curve:
    """Extract a profile (line section) from the image"""
    h, w = img.shape[:2]

    # Convert to grayscale for profile
    gray = img.mean(axis=2)

    if profile_direction == "horizontal":
        # Horizontal line through the image
        line_idx = int(profile_line * (h - 1))
        profile_values = gray[line_idx, :]
        x_coords = np.arange(w)
        label = f"Horizontal profile at y={line_idx}"
    elif profile_direction == "vertical":
        # Vertical line through the image
        line_idx = int(profile_line * (w - 1))
        profile_values = gray[:, line_idx]
        x_coords = np.arange(h)
        label = f"Vertical profile at x={line_idx}"
    else:  # diagonal
        # Diagonal line from top-left to bottom-right
        num_points = int(np.sqrt(h**2 + w**2))
        x_indices = np.linspace(0, w - 1, num_points).astype(int)
        y_indices = (profile_line * h + (1 - profile_line) * (h - 1) * x_indices / (w - 1)).astype(int)
        y_indices = np.clip(y_indices, 0, h - 1)
        profile_values = gray[y_indices, x_indices]
        x_coords = np.linspace(0, np.sqrt(h**2 + w**2), num_points)
        label = f"Diagonal profile (offset={profile_line:.2f})"

    curve = Curve(
        [
            [x_coords, profile_values, "b-", label],
        ],
        xlabel=("Position [pixels]" if profile_direction != "diagonal" else "Distance [pixels]"),
        ylabel="Intensity",
        ylim=(0.0, 1.0),
        grid=True,
        title=f"Image Profile ({profile_direction})",
    )

    layout.style("profile", title=f"Profile: {profile_direction} at {profile_line:.2f}")

    return curve


@interactive(
    num_bins=(50, [10, 200]),  # Int slider for histogram bins
    channel=Control("grayscale", ["grayscale", "red", "green", "blue"]),  # Dropdown for channel
)
def compute_histogram(
    img: np.ndarray,
    num_bins: int = 50,
    channel: str = "grayscale",
) -> Curve:
    """Compute histogram of the image"""
    if channel == "grayscale":
        values = img.mean(axis=2).flatten()
        color = "k-"
        label = "Grayscale"
    elif channel == "red":
        values = img[:, :, 0].flatten()
        color = "r-"
        label = "Red"
    elif channel == "green":
        values = img[:, :, 1].flatten()
        color = "g-"
        label = "Green"
    else:  # blue
        values = img[:, :, 2].flatten()
        color = "b-"
        label = "Blue"

    # Compute histogram
    hist, bin_edges = np.histogram(values, bins=num_bins, range=(0.0, 1.0))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    # Normalize histogram to [0, 1] for display
    hist_normalized = hist.astype(np.float32) / hist.max() if hist.max() > 0 else hist

    curve = Curve(
        [
            [bin_centers, hist_normalized, color, label],
        ],
        xlabel="Pixel Intensity",
        ylabel="Normalized Frequency",
        ylim=(0.0, 1.0),
        grid=True,
        title=f"Image Histogram ({num_bins} bins)",
    )

    layout.style("histogram", title=f"Histogram: {channel} channel ({num_bins} bins)")

    return curve


@interactive(
    layout_mode=Control("horizontal", ["horizontal", "vertical"]),
)
def change_layout(layout_mode: str = "horizontal") -> None:
    if layout_mode == "horizontal":
        layout.grid(["image", "profile", "histogram"])
    elif layout_mode == "vertical":
        layout.grid([["image"], ["profile"], ["histogram"]])


def image_analysis_pipeline():
    """Main pipeline function showcasing image with dependent curves"""
    image = generate_image()
    profile = extract_profile(image)
    histogram = compute_histogram(image)
    change_layout()
    return [image, profile, histogram]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Analysis demo with profile and histogram curves")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb", "headless"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()

    image_analysis_pipeline_interactive = interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Image Analysis Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(image_analysis_pipeline)
    outputs = image_analysis_pipeline_interactive()
    if args.backend == "headless":
        image_analysis_pipeline_interactive.graph_representation(path="image_analysis_pipeline")
        outputs[1].show()
        outputs[2].show()
