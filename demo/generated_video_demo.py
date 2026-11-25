"""
Demo: a filter that returns a ``Video``, here a bouncing ball simulation.

``simulate`` integrates the flight of a ball thrown into a box (launch angle
and speed, gravity, bounciness, air drag) and renders every frame. It returns
the clip as a ``Video``, so the window gets a timeline: scrub it, press
<kbd>Space</kbd> to play, step with the arrows. The filters after it receive
the frame under the playhead:

- ``overlay`` draws the trail flown so far and the velocity vector;
- ``energy_plot`` plots the height and the energy, with a dot at the
  current instant.

Moving the playhead never runs the simulation again: only ``overlay`` and
``energy_plot`` re-run. Change a slider of ``simulate`` and the clip is
simulated again; the timeline follows its new duration and frame rate.

    python demo/generated_video_demo.py          # Qt
    python demo/generated_video_demo.py -b dpg   # Dear PyGui
"""

import argparse
import time

import cv2
import numpy as np

from interactive_pipe import Curve, SingleCurve, Video, context, interactive, interactive_pipeline, layout

WIDTH, HEIGHT = 480, 300  # pixels, 100 pixels per meter
SCALE = 100.0
RADIUS = 0.12  # meters


def _to_pixels(x: float, y: float):
    return int(round(x * SCALE)), int(round(HEIGHT - y * SCALE))


def _box() -> np.ndarray:
    """The empty box: a dark background, a floor and a 0.5 m grid."""
    canvas = np.full((HEIGHT, WIDTH, 3), 0.08, np.float32)
    for x in range(0, WIDTH, 50):
        cv2.line(canvas, (x, 0), (x, HEIGHT), (0.16, 0.16, 0.16), 1)
    for y in range(HEIGHT, 0, -50):
        cv2.line(canvas, (0, y), (WIDTH, y), (0.16, 0.16, 0.16), 1)
    cv2.rectangle(canvas, (0, 0), (WIDTH - 1, HEIGHT - 1), (0.6, 0.6, 0.6), 2)
    return canvas


@interactive(
    angle=(55.0, [5.0, 85.0], "launch angle (deg)"),
    speed=(6.0, [1.0, 12.0], "launch speed (m/s)"),
    gravity=(9.81, [1.0, 25.0], "gravity (m/s²)"),
    bounciness=(0.8, [0.1, 1.0]),
    drag=(0.05, [0.0, 1.0], "air drag (1/s)"),
    duration=(4.0, [1.0, 10.0], "duration (s)"),
    fps=(25.0, [5.0, 60.0]),
)
def simulate(angle=55.0, speed=6.0, gravity=9.81, bounciness=0.8, drag=0.05, duration=4.0, fps=25.0):
    """Fly the ball and render every frame: returns the clip and the trajectory."""
    start = time.perf_counter()
    n_frames = max(2, int(round(duration * fps)))
    substeps = 20
    dt = 1.0 / (fps * substeps)
    width_m, height_m = WIDTH / SCALE, HEIGHT / SCALE
    position = np.array([RADIUS + 0.05, RADIUS + 0.05])
    velocity = speed * np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])
    states = np.empty((n_frames, 4))  # x, y, vx, vy at each frame
    for k in range(n_frames):
        states[k] = (*position, *velocity)
        for _ in range(substeps):
            velocity = velocity + dt * (np.array([0.0, -gravity]) - drag * velocity)
            position = position + dt * velocity
            for axis, limit in enumerate((width_m, height_m)):
                if position[axis] < RADIUS and velocity[axis] < 0:
                    position[axis], velocity[axis] = RADIUS, -bounciness * velocity[axis]
                elif position[axis] > limit - RADIUS and velocity[axis] > 0:
                    position[axis], velocity[axis] = limit - RADIUS, -bounciness * velocity[axis]
    background = _box()
    frames = np.empty((n_frames, HEIGHT, WIDTH, 3), np.float32)
    for k, (x, y, _, _) in enumerate(states):
        frame = background.copy()
        cv2.circle(frame, _to_pixels(x, y), int(RADIUS * SCALE), (0.2, 0.55, 1.0), -1, cv2.LINE_AA)
        frames[k] = frame
    elapsed = 1000.0 * (time.perf_counter() - start)
    trajectory = {"states": states, "gravity": gravity, "fps": fps, "elapsed_ms": elapsed}
    return Video(frames, fps=fps), trajectory


def overlay(frame, trajectory):
    """The trail flown so far and the velocity vector, at the current frame."""
    timeline = context["timeline"]
    states = trajectory["states"]
    k = min(timeline.frame, len(states) - 1)
    out = frame.copy()
    trail = np.array([_to_pixels(x, y) for x, y, _, _ in states[: k + 1]], np.int32)
    if len(trail) > 1:
        cv2.polylines(out, [trail], False, (1.0, 0.75, 0.2), 1, cv2.LINE_AA)
    x, y, vx, vy = states[k]
    tip = _to_pixels(x + 0.08 * vx, y + 0.08 * vy)
    cv2.arrowedLine(out, _to_pixels(x, y), tip, (0.3, 1.0, 0.4), 2, cv2.LINE_AA, tipLength=0.25)
    layout.style(
        "ball",
        title=f"t = {k / trajectory['fps']:4.2f} s   |v| = {np.hypot(vx, vy):4.1f} m/s"
        f"   (simulated in {trajectory['elapsed_ms']:.0f} ms)",
    )
    return out


def energy_plot(trajectory):
    """Height and energy per kilogram over the clip, a dot at the current frame."""
    states = trajectory["states"]
    t = np.arange(len(states)) / trajectory["fps"]
    height = states[:, 1] - RADIUS
    energy = trajectory["gravity"] * height + 0.5 * (states[:, 2] ** 2 + states[:, 3] ** 2)
    k = min(context["timeline"].frame, len(states) - 1)
    return Curve(
        [
            SingleCurve(t, height, style="b-", label="height (m)"),
            SingleCurve(t, energy / 10.0, style="r-", label="energy (J/kg / 10)"),
            SingleCurve([t[k]], [height[k]], style="bo", markersize=8),
            SingleCurve([t[k]], [energy[k] / 10.0], style="ro", markersize=8),
        ],
        xlabel="time (s)",
        grid=True,
        title="energy lost at each bounce",
    )


def bouncing_ball_lab():
    clip, trajectory = simulate()
    ball = overlay(clip, trajectory)
    energy = energy_plot(trajectory)
    return [ball, energy]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-b", "--backend", choices=["qt", "dpg"], default="qt")
    args = parser.parse_args()
    interactive_pipeline(gui=args.backend, cache="graph", name="Bouncing ball lab")(bouncing_ball_lab)()
