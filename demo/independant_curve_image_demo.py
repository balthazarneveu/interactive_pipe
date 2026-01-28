"""
Demo showcasing a curve and an image with multiple sliders.

This demo demonstrates:
- Curve visualization with adjustable parameters
- Image generation/processing with adjustable parameters
- Multiple float and int sliders controlling both outputs
- Side-by-side display of curve and image
"""

import argparse

import numpy as np

from interactive_pipe import interactive, interactive_pipeline, layout
from interactive_pipe.data_objects.curves import Curve


@interactive(
    frequency=(2.0, [0.5, 10.0]),  # Float slider for curve frequency
    amplitude=(1.0, [0.1, 2.0]),  # Float slider for curve amplitude
    phase=(0.0, [0.0, 360.0]),  # Float slider for phase in degrees
    num_points=(100, [50, 500]),  # Int slider for number of curve points
)
def generate_curve(
    frequency: float = 2.0,
    amplitude: float = 1.0,
    phase: float = 0.0,
    num_points: int = 100,
) -> Curve:
    """Generate a mathematical curve with adjustable parameters"""
    x = np.linspace(0.0, 4.0 * np.pi, num_points)
    phase_rad = np.deg2rad(phase)

    # Main curve: sine wave
    y_main = amplitude * np.sin(frequency * x + phase_rad)

    # Reference curve: cosine wave
    y_ref = amplitude * np.cos(frequency * x)

    curve = Curve(
        [
            [x, y_main, "b-", f"sin({frequency:.2f}×x + {phase:.0f}°)"],
            [x, y_ref, "r--", f"cos({frequency:.2f}×x)"],
        ],
        xlabel="x [rad]",
        ylabel="y",
        ylim=[-2.5, 2.5],
        grid=True,
        title=f"Oscillations (A={amplitude:.2f}, f={frequency:.2f} Hz)",
    )

    layout.style("curve", title=f"Curve: f={frequency:.2f}, A={amplitude:.2f}, φ={phase:.0f}°")

    return curve


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


def curve_image_pipeline():
    """Main pipeline function showcasing curve and image side by side"""
    curve = generate_curve()
    image = generate_image()
    return [curve, image]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Curve and Image demo with multiple sliders")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, or nb (default: qt)",
    )
    args = parser.parse_args()

    interactive_pipeline(
        gui=args.backend,
        cache=False,
        name="Curve & Image Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(curve_image_pipeline)()
