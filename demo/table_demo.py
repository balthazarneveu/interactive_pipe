"""
Demo showcasing Table data type with image statistics.

This demo demonstrates:
- Table visualization with adjustable parameters
- Image generation/processing with adjustable parameters
- Computing statistics from image data and displaying in tabular format
- Side-by-side display of image and statistics table
"""

import numpy as np
import argparse
from interactive_pipe import interactive, interactive_pipeline
from interactive_pipe.data_objects.table import Table


@interactive(
    noise_level=(0.1, [0.0, 0.5]),  # Float slider for noise level
    brightness=(0.5, [0.0, 1.0]),  # Float slider for brightness
    image_size=(200, [100, 400]),  # Int slider for image size
)
def generate_noisy_image(
    noise_level: float = 0.1, brightness: float = 0.5, image_size: int = 200
):
    """Generate a test image with adjustable noise and brightness."""
    img = np.ones((image_size, image_size, 3)) * brightness
    img += np.random.randn(*img.shape) * noise_level
    return np.clip(img, 0, 1)


@interactive()
def compute_statistics(img, global_params={}):
    """Compute per-channel statistics and return as Table."""
    channels = ["Red", "Green", "Blue"]
    stats = {
        "Channel": channels,
        "Mean": [f"{img[:, :, i].mean():.4f}" for i in range(3)],
        "Std": [f"{img[:, :, i].std():.4f}" for i in range(3)],
        "Min": [f"{img[:, :, i].min():.4f}" for i in range(3)],
        "Max": [f"{img[:, :, i].max():.4f}" for i in range(3)],
    }
    table = Table(stats, title="Image Statistics", precision=4)
    
    global_params["__output_styles"]["stats"] = {
        "title": "Channel Statistics"
    }
    
    return table


def table_pipeline():
    """Main pipeline function showcasing image and statistics table side by side."""
    img = generate_noisy_image()
    stats = compute_statistics(img)
    return [[img, stats]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Table demo with image statistics")
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
        name="Table Demo",
        size=(10, 10) if args.backend == "nb" else None,
    )(table_pipeline)()
