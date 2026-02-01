"""Physics animation demo showcasing TimeControl with bouncing balls."""

import argparse

import cv2
import numpy as np

from interactive_pipe import TimeControl, interactive, interactive_pipeline


@interactive(
    time=TimeControl(update_interval_ms=50),
    gravity=(1.0, [0.1, 2.0]),
    n_balls=(5, [1, 10]),
    speed=(1.0, [0.1, 3.0]),
)
def bouncing_balls(time=0.0, gravity=1.0, n_balls=5, speed=1.0):
    """Simulate bouncing balls with gravity and elastic collisions."""
    # Canvas setup
    size = 512
    canvas = np.zeros((size, size, 3), dtype=np.float32)

    # Ball properties
    np.random.seed(42)  # Reproducible positions
    radius = 15

    # Apply speed multiplier to time
    effective_time = time * speed

    # Initialize or update ball states
    balls = []
    for i in range(int(n_balls)):
        # Use time and index for deterministic but varied motion
        phase_x = i * 0.7

        # Position oscillates based on time
        base_x = size // 2 + 150 * np.sin(effective_time * 0.5 + phase_x)

        # Add bouncing motion with gravity
        bounce_height = 200 * abs(np.sin(effective_time * gravity * 0.5 + i * 0.5))
        y = size - radius - bounce_height
        x = base_x

        # Clamp to canvas
        x = np.clip(x, radius, size - radius)
        y = np.clip(y, radius, size - radius)

        # Color based on index (in [0, 1] range)
        hue = (i * 40) % 180
        color = cv2.cvtColor(np.uint8([[[hue, 255, 255]]]), cv2.COLOR_HSV2BGR)[0, 0] / 255.0
        color = tuple(float(c) for c in color)

        balls.append((int(x), int(y), color))

    # Draw balls
    for x, y, color in balls:
        cv2.circle(canvas, (x, y), radius, color, -1)
        cv2.circle(canvas, (x, y), radius, (1.0, 1.0, 1.0), 2)  # White outline

    # Add grid for reference
    for i in range(0, size, 64):
        cv2.line(canvas, (i, 0), (i, size), (0.12, 0.12, 0.12), 1)
        cv2.line(canvas, (0, i), (size, i), (0.12, 0.12, 0.12), 1)

    return canvas


def pipeline():
    result = bouncing_balls()
    return [result]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Physics animation demo with TimeControl")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio"],
        default="qt",
        help="Backend to use: qt or gradio (default: qt)",
    )
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache=False)(pipeline)()
