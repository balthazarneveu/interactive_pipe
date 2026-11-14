"""Gyroscope video stabilization: counter-rotate each frame towards a smoothed camera path.

The gyro measures angular rate; integrating it gives the camera orientation R(t). A virtual
camera follows a smoothed path R_smooth(t), and each frame is re-projected into it with the
homography K R_smooth R(t)^T K^-1 (see camera_rotation.py). The re-projected frame no longer
covers the whole field of view: the black borders are hidden by cropping, and the zoom is
the price paid. The steadier the path, the bigger the zoom.

    python gyro_stabilization.py             # interactive window (press v to export a GIF)
    python gyro_stabilization.py out.gif     # no window: render the stabilized view to a GIF
"""

import sys

import numpy as np
from camera_rotation import checkerboard, intrinsics, rotation, warp

from interactive_pipe import Curve, TimeControl, export_animation, interactive, interactive_pipeline, layout

FRAME_H, FRAME_W, FOCAL = 270, 480, 400.0  # 62 deg horizontal field of view
SCENE_H, SCENE_W = 400, 1000  # the fixed scene, as seen by the camera at rest
FPS, DURATION, PAN = 25, 8.0, -24.0  # the operator pans 24 deg to the left over the clip
K, K_SCENE = intrinsics(FOCAL, FRAME_W, FRAME_H), intrinsics(FOCAL, SCENE_W, SCENE_H)
CENTRE = np.array([FRAME_W / 2, FRAME_H / 2])
CORNERS = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]]) * CENTRE
ZOOMS = np.linspace(1.0, 3.0, 401)
GIF = sys.argv[1] if len(sys.argv) > 1 else None


def stabilizing(raw, smooth):
    """Shaky frame -> virtual camera on the smooth path: undo R(t), then apply R_smooth."""
    return K @ rotation(*smooth) @ rotation(*raw).T @ np.linalg.inv(K)


def zoom_about_centre(zoom):
    return np.array([[zoom, 0, (1 - zoom) * CENTRE[0]], [0, zoom, (1 - zoom) * CENTRE[1]], [0, 0, 1]])


def zoom_needed(homography):
    """Smallest centred crop zoom whose four corners all come from inside the shaky frame."""
    corners = CORNERS[None] / ZOOMS[:, None, None] + CENTRE  # (zoom, corner, xy)
    src = np.concatenate([corners, np.ones((*corners.shape[:2], 1))], -1) @ np.linalg.inv(homography).T
    x, y = src[..., 0] / src[..., 2], src[..., 1] / src[..., 2]
    inside = ((src[..., 2] > 0) & (x >= 0) & (x <= FRAME_W) & (y >= 0) & (y <= FRAME_H)).all(axis=1)
    return ZOOMS[inside.argmax()] if inside.any() else np.inf


@interactive()
def fixed_scene():
    return checkerboard(SCENE_H, SCENE_W, cell=40)


@interactive()
def gyroscope():
    """Angular rates (deg/s) of a hand-held camera, integrated once into yaw, pitch, roll."""
    t = np.arange(int(DURATION * FPS))[:, None, None] / FPS
    rng = np.random.default_rng(7)
    freq, phase, amplitude = rng.uniform(1, 5, (6, 3)), rng.uniform(0, 2 * np.pi, (6, 3)), rng.uniform(0.2, 0.8, (6, 3))
    tremor = (amplitude * 2 * np.pi * freq * np.cos(2 * np.pi * freq * t + phase)).sum(axis=1)
    pan = PAN / DURATION * (1 - np.cos(2 * np.pi * t[:, 0] / DURATION)) * [1, 0, 0]  # starts and stops smoothly
    # Small-angle shortcut: each rate axis is integrated on its own into yaw / pitch / roll
    return np.cumsum(tremor + pan, axis=0) / FPS - [PAN / 2, 0, 0]


@interactive(smoothing=(0.5, [0.0, 1.0], "path smoothing (0 off, 1 locked)"))
def smooth_path(angles, smoothing=0.5):
    """Gaussian-weighted average of the whole path (offline): sigma grows to infinity at 1 (locked)."""
    t = np.arange(len(angles)) / FPS
    sigma = 1e-3 + smoothing / max(1 - smoothing, 1e-6)  # seconds
    weights = np.exp(-0.5 * ((t[:, None] - t[None, :]) / sigma) ** 2)
    smooth = weights @ angles / weights.sum(axis=1, keepdims=True)
    return smooth, np.array([zoom_needed(stabilizing(*pair)) for pair in zip(angles, smooth)])


@interactive(time=TimeControl(name="time", update_interval_ms=40))
def clock(time=0.0):
    return int(round(time * FPS)) % int(DURATION * FPS)


@interactive()
def shaky_view(scene, angles, frame):
    layout.style("shaky", title=f"Hand-held camera, t = {frame / FPS:.2f} s")
    return warp(scene, K @ rotation(*angles[frame]) @ np.linalg.inv(K_SCENE), size=(FRAME_H, FRAME_W))


@interactive(zoom=(1.25, [1.0, 2.0], "crop zoom"))
def stabilize(shaky, angles, smooth, zooms, frame, zoom=1.25):
    homography = stabilizing(angles[frame], smooth[frame])
    stabilized = warp(shaky, homography)
    x0, y0 = (CENTRE * (1 - 1 / zoom)).astype(int)  # the crop rectangle, drawn in green
    box = stabilized[y0 : FRAME_H - y0, x0 : FRAME_W - x0]
    box[[0, 1, -2, -1]] = box[:, [0, 1, -2, -1]] = (0.1, 1.0, 0.2)
    layout.style("stabilized", title=f"Stabilized: zoom >= {zooms[frame]:.2f} hides the borders now")
    layout.style("cropped", title=f"Cropped x{zoom:.2f} (whole clip needs x{zooms.max():.2f})")
    return stabilized, warp(shaky, zoom_about_centre(zoom) @ homography)


@interactive()
def plot_path(angles, smooth, frame):
    t, names = np.arange(len(angles)) / FPS, ("yaw", "pitch", "roll")
    raw = [(t, angles[:, i], {"style": f"C{i}-", "alpha": 0.5}) for i in range(3)]
    path = [(t, smooth[:, i], f"C{i}--", name) for i, name in enumerate(names)]
    now = ([t[frame]] * 2, [-15, 15], "k-")
    title = "Camera path: integrated gyro (solid), smoothed (dashed)"
    return Curve(raw + path + [now], xlabel="time (s)", ylabel="angle (deg)", title=title, grid=True)


@interactive_pipeline(gui=None if GIF else "auto", cache="graph")
def gyro_stabilization():
    scene = fixed_scene()
    angles = gyroscope()
    smooth, zooms = smooth_path(angles)
    frame = clock()
    shaky = shaky_view(scene, angles, frame)
    stabilized, cropped = stabilize(shaky, angles, smooth, zooms, frame)
    path = plot_path(angles, smooth, frame)
    return [[shaky, stabilized], [cropped, path]]


if __name__ == "__main__":
    gyro_stabilization()  # opens the window, or runs once headless when a GIF path is given
    if GIF:
        export_animation(gyro_stabilization, GIF, duration=DURATION, fps=FPS / 2, output=(0, 1))
