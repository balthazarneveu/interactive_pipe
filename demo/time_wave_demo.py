"""Wave interference demo showcasing TimeControl with sine wave patterns."""

import argparse

import cv2
import numpy as np

from interactive_pipe import TimeControl, interactive, interactive_pipeline, layout


@interactive(
    time=TimeControl(update_interval_ms=50),
    freq1=(2.0, [0.5, 5.0]),
    freq2=(3.0, [0.5, 5.0]),
    amplitude=(1.0, [0.1, 2.0]),
)
def wave_interference(time=0.0, freq1=2.0, freq2=3.0, amplitude=1.0):
    """Generate wave interference patterns with multiple visualizations."""
    # 1D Wave plot
    width, height_1d = 512, 200
    canvas_1d = np.ones((height_1d, width, 3), dtype=np.float32)

    x = np.linspace(0, 4 * np.pi, width)
    wave1 = amplitude * np.sin(freq1 * x - time * 2)
    wave2 = amplitude * np.sin(freq2 * x - time * 2)
    interference = wave1 + wave2

    # Draw waves
    center_y = height_1d // 2
    scale = 50

    # Grid
    cv2.line(canvas_1d, (0, center_y), (width, center_y), (0.78, 0.78, 0.78), 1)

    # Wave 1 (red)
    for i in range(width - 1):
        y1 = int(center_y - wave1[i] * scale)
        y2 = int(center_y - wave1[i + 1] * scale)
        cv2.line(canvas_1d, (i, y1), (i + 1, y2), (0.4, 0.4, 1.0), 2)

    # Wave 2 (blue)
    for i in range(width - 1):
        y1 = int(center_y - wave2[i] * scale)
        y2 = int(center_y - wave2[i + 1] * scale)
        cv2.line(canvas_1d, (i, y1), (i + 1, y2), (1.0, 0.4, 0.4), 2)

    # Interference (black)
    for i in range(width - 1):
        y1 = int(center_y - interference[i] * scale)
        y2 = int(center_y - interference[i + 1] * scale)
        cv2.line(canvas_1d, (i, y1), (i + 1, y2), (0.0, 0.0, 0.0), 3)

    layout.style("wave_1d", title="1D Wave Interference")

    # 2D Ripple interference
    size = 512
    canvas_2d = np.zeros((size, size), dtype=np.float32)

    # Create coordinate grids
    y_grid, x_grid = np.ogrid[:size, :size]

    # Two wave sources
    cx1, cy1 = size // 3, size // 2
    cx2, cy2 = 2 * size // 3, size // 2

    # Distance from sources
    dist1 = np.sqrt((x_grid - cx1) ** 2 + (y_grid - cy1) ** 2)
    dist2 = np.sqrt((x_grid - cx2) ** 2 + (y_grid - cy2) ** 2)

    # Wave propagation
    wave_2d_1 = amplitude * np.sin(freq1 * dist1 / 30 - time * 2)
    wave_2d_2 = amplitude * np.sin(freq2 * dist2 / 30 - time * 2)
    interference_2d = wave_2d_1 + wave_2d_2

    # Normalize and convert to color
    interference_2d = (interference_2d + 2 * amplitude) / (4 * amplitude)
    canvas_2d = np.clip(interference_2d * 255, 0, 255).astype(np.uint8)
    canvas_2d_color = cv2.applyColorMap(canvas_2d, cv2.COLORMAP_JET).astype(np.float32) / 255.0

    # Mark wave sources
    cv2.circle(canvas_2d_color, (cx1, cy1), 8, (1.0, 1.0, 1.0), -1)
    cv2.circle(canvas_2d_color, (cx2, cy2), 8, (1.0, 1.0, 1.0), -1)

    layout.style("wave_2d", title="2D Wave Interference")

    return canvas_1d, canvas_2d_color


def pipeline():
    wave_1d, wave_2d = wave_interference()
    return [wave_1d, wave_2d]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wave interference demo with TimeControl")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "dpg"],
        default="qt",
        help="Backend to use: qt, gradio, or dpg (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=False)(pipeline)()
