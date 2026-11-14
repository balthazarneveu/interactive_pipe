"""A pinhole camera rotating in place: the image is warped by the homography K R K^-1.

No depth is needed for a pure rotation: every pixel is a viewing ray, and rotating
the camera only re-projects those rays. The same angle moves the image by f*tan(angle)
pixels, so a long focal moves it more, and a wide field of view stretches the edges.
"""

import numpy as np

from interactive_pipe import interactive, interactive_pipeline, layout

HEIGHT, WIDTH = 384, 512
NO_DATA = (1.0, 0.0, 1.0)  # magenta: rays that the source image never saw


def checkerboard(height, width, cell=32):
    """Checkerboard whose tint encodes the position: red grows to the right, blue downwards."""
    y, x = np.mgrid[:height, :width] + 0.5
    tint = np.stack([x / width, 0.35 + 0 * x, y / height], axis=-1)
    dark = ((x // cell + y // cell) % 2 == 1)[..., None]
    board = np.where(dark, 0.6 * tint, 0.45 + 0.55 * tint)
    board[(np.abs(x - width / 2) < 2) | (np.abs(y - height / 2) < 2)] = 1.0  # cross on the optical axis
    return board


def intrinsics(focal_px, width, height):
    """Pinhole matrix K: square pixels, principal point at the image centre."""
    return np.array([[focal_px, 0.0, width / 2], [0.0, focal_px, height / 2], [0.0, 0.0, 1.0]])


def rotation(yaw, pitch, roll):
    """World-to-camera rotation of a camera turned by yaw (right), pitch (up), roll (clockwise), in degrees."""
    cy, sy, cp, sp, cr, sr = (f(np.radians(a)) for a in (yaw, pitch, roll) for f in (np.cos, np.sin))
    turn_right = np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]])
    tilt_up = np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])  # image y points down
    spin = np.array([[cr, sr, 0], [-sr, cr, 0], [0, 0, 1]])
    return spin @ tilt_up @ turn_right  # yaw first, then pitch, then roll about the new optical axis


def warp(image, homography, fill=(0.0, 0.0, 0.0), size=None):
    """Output pixel p shows source pixel H^-1 p (inverse mapping), bilinearly interpolated."""
    (height, width), (src_h, src_w) = size or image.shape[:2], image.shape[:2]
    y, x = np.mgrid[:height, :width] + 0.5  # pixel centres
    src = np.linalg.inv(homography) @ np.stack([x.ravel(), y.ravel(), np.ones(x.size)])
    with np.errstate(divide="ignore", invalid="ignore"):
        sx, sy = src[0] / src[2] - 0.5, src[1] / src[2] - 0.5
    valid = (src[2] > 0) & (sx >= 0) & (sx <= src_w - 1) & (sy >= 0) & (sy <= src_h - 1)
    sx, sy = np.where(valid, sx, 0), np.where(valid, sy, 0)
    x0, y0 = np.minimum(sx.astype(int), src_w - 2), np.minimum(sy.astype(int), src_h - 2)
    ax, ay = (sx - x0)[:, None], (sy - y0)[:, None]
    pixels, i = image.reshape(-1, image.shape[2]), y0 * src_w + x0  # flat indices: take() is fast
    top = (1 - ax) * pixels.take(i, axis=0) + ax * pixels.take(i + 1, axis=0)
    bottom = (1 - ax) * pixels.take(i + src_w, axis=0) + ax * pixels.take(i + src_w + 1, axis=0)
    return np.where(valid[:, None], (1 - ay) * top + ay * bottom, fill).reshape(height, width, -1)


@interactive()
def scene():
    layout.style("source", title="Source: camera at rest")
    return checkerboard(HEIGHT, WIDTH)


@interactive(
    yaw=(15.0, [-60.0, 60.0], "yaw (deg)"),
    pitch=(0.0, [-45.0, 45.0], "pitch (deg)"),
    roll=(0.0, [-180.0, 180.0], "roll (deg)"),
    focal_mm=(20.0, [10.0, 150.0], "focal (mm, full-frame eq.)"),
)
def rotate_camera(source, yaw=15.0, pitch=0.0, roll=0.0, focal_mm=20.0):
    focal_px = focal_mm / 36.0 * WIDTH  # a 36 mm wide sensor spans the image width
    K = intrinsics(focal_px, WIDTH, HEIGHT)
    fov = 2 * np.degrees(np.arctan(WIDTH / 2 / focal_px))
    shift = focal_px * np.tan(np.radians(yaw))
    layout.style("rotated", title=f"K R K^-1   FOV {fov:.0f} deg   centre moves f*tan(yaw) = {abs(shift):.0f} px")
    rotated = warp(source, K @ rotation(yaw, pitch, roll) @ np.linalg.inv(K), fill=NO_DATA)
    cy, cx = HEIGHT // 2, WIDTH // 2  # yellow cross: the optical axis of the rotated camera
    rotated[cy - 9 : cy + 9, cx - 1 : cx + 1] = rotated[cy - 1 : cy + 1, cx - 9 : cx + 9] = (1.0, 0.9, 0.0)
    return rotated


@interactive_pipeline()
def camera_rotation():
    source = scene()
    rotated = rotate_camera(source)
    return source, rotated


if __name__ == "__main__":
    camera_rotation()
