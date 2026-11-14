"""A minimal camera pipeline (ISP): raw Bayer mosaic -> black level -> demosaic -> white balance -> gamma.

The sensor adds a constant offset (black level) and sees the scene through one
colour filter per photosite (RGGB). Every stage up to white balance is linear, and
white balance multiplies: it must scale light only, not the sensor offset, and not
gamma-encoded values. Get the black level or the stage order wrong and the grey
ramp at the bottom stops being grey, mostly in the shadows.
"""

import numpy as np

from interactive_pipe import Curve, interactive, interactive_pipeline, layout

HEIGHT, WIDTH, WHITE_LEVEL, SENSOR_BLACK = 256, 384, 1023, 64  # 10-bit sensor, values in DN
TUNGSTEN = np.array([1 / 1.6, 1.0, 1 / 2.5])  # raw response to white: the right gains are R x1.6, B x2.5
CHECKER = np.array(  # ColorChecker patches, 8-bit sRGB, 4 rows of 6
    "115 82 68 194 150 130 98 122 157 87 108 67 133 128 177 103 189 170 214 126 44 80 91 166 193 90 99 94 60 108 "
    "157 188 64 224 163 46 56 61 150 70 148 73 175 54 60 231 199 31 187 86 149 8 133 161 243 243 242 200 200 200 "
    "160 160 160 122 122 121 85 85 85 52 52 52".split(),
    dtype=float,
).reshape(4, 6, 3)
BAYER = np.zeros((HEIGHT, WIDTH, 3))  # which colour each photosite sees: RGGB
BAYER[::2, ::2, 0] = BAYER[::2, 1::2, 1] = BAYER[1::2, ::2, 1] = BAYER[1::2, 1::2, 2] = 1
RAMP, STAR = slice(196, 244), (88, 326)  # rows of the grey ramp, centre of the Siemens star
ORDERS = ["after black level (correct)", "before black level", "after gamma"]


def scene():  # linear reflectances: colour checker, Siemens star (fine detail), grey ramp
    y, x = np.mgrid[:HEIGHT, :WIDTH]
    img = np.full((HEIGHT, WIDTH, 3), 0.18)
    patches = (y < 176) & (x < 264) & (y % 44 >= 6) & (x % 44 >= 6)
    img[patches] = (CHECKER[y[patches] // 44, x[patches] // 44] / 255) ** 2.2
    dy, dx = y - STAR[0], x - STAR[1]
    star = np.hypot(dx, dy) < 54
    img[star] = np.where(np.sin(18 * np.arctan2(dy, dx)) > 0, 0.85, 0.03)[star, None]
    img[RAMP] = 0.95 * (x[RAMP, :, None] / (WIDTH - 1)) ** 2.2  # even steps once gamma-encoded
    return img


def sensor(img):
    """Tungsten light, one colour per photosite, shot + read noise, black offset, 10-bit quantization."""
    light = (img * TUNGSTEN * BAYER).sum(-1) * (WHITE_LEVEL - SENSOR_BLACK)
    noisy = light + np.random.default_rng(0).normal(size=light.shape) * np.sqrt(0.5 * light + 4)
    return np.clip(np.round(noisy + SENSOR_BLACK), 0, WHITE_LEVEL)


def show_raw(raw):
    layout.style("raw_view", title=f"Raw mosaic as stored: one value per photosite, black at {SENSOR_BLACK} DN")
    return raw / WHITE_LEVEL


@interactive(black_level=(SENSOR_BLACK, [0, 128], "black level to subtract (DN)", "1. Black level"))
def subtract_black_level(raw, black_level=SENSOR_BLACK):
    # no clipping: the noise in the dark stays unbiased. `offset` is the black level in the new units.
    return (raw - black_level) / (WHITE_LEVEL - black_level), black_level / (WHITE_LEVEL - black_level)


@interactive(method=("bilinear", ["bilinear", "half resolution"], "demosaic method", "2. Demosaic"))
def demosaic(mosaic, method="bilinear"):
    layout.style("demosaiced", title=f"Demosaiced ({method}): linear, raw sensor colours under tungsten")
    if method == "half resolution":  # one RGB pixel per 2x2 block, although R, G and B were not seen at the same spot
        rgb = np.stack([mosaic[::2, ::2], (mosaic[::2, 1::2] + mosaic[1::2, ::2]) / 2, mosaic[1::2, 1::2]], -1)
        return rgb.repeat(2, 0).repeat(2, 1)
    # bilinear: a missing sample is the average of its nearest neighbours of the same colour
    rb, g = np.outer([1, 2, 1], [1, 2, 1]) / 4, np.array([[0, 1, 0], [1, 4, 1], [0, 1, 0]]) / 4
    kernels = np.stack([rb, g, rb], -1)  # (3, 3, channel)
    padded = np.pad(mosaic[..., None] * BAYER, ((1, 1), (1, 1), (0, 0)), mode="reflect")  # keeps the Bayer phase
    return sum(kernels[i, j] * padded[i : i + HEIGHT, j : j + WIDTH] for i in range(3) for j in range(3))


@interactive(
    red_gain=(1.6, [0.5, 4.0], "red gain", "3. White balance"),
    blue_gain=(2.5, [0.5, 4.0], "blue gain", "3. White balance"),
    grey_world=(False, "auto (grey world)", "3. White balance"),
    order=(ORDERS[0], ORDERS, "apply white balance", "3. White balance"),
)
def white_balance(rgb, offset, red_gain=1.6, blue_gain=2.5, grey_world=False, order=ORDERS[0]):
    """Returns the balanced image and the gains left to apply after gamma (all 1 unless order is 'after gamma')."""
    means = rgb.reshape(-1, 3).mean(0)
    gains = means[1] / means if grey_world else np.array([red_gain, 1.0, blue_gain])
    if order == ORDERS[2]:
        layout.style("balanced", title="Not balanced yet: gains applied after gamma act like gains**gamma")
        return rgb, gains
    # before black level: the gains also multiply the offset, which is then subtracted as if unchanged
    leftover = (gains - 1) * offset if order == ORDERS[1] else 0 * gains
    title = f"White balanced (linear): R x{gains[0]:.2f} B x{gains[2]:.2f}"
    layout.style("balanced", title=f"{title}, offset left R {leftover[0]:+.3f} B {leftover[2]:+.3f}")
    return gains * rgb + leftover, np.ones(3)


@interactive(gamma=(2.2, [1.0, 3.0], "gamma", "4. Gamma"))
def gamma_encode(balanced, late_gains, gamma=2.2):
    layout.style("final", title=f"Final: encoded with x^(1/{gamma:.1f}), shadows brightened")
    return np.clip(late_gains * np.clip(balanced, 0, 1) ** (1 / gamma), 0, 1)


def zoom(raw, final, half=24, factor=4):
    layout.style("detail", title=f"Siemens star centre x{factor}: raw mosaic in its filter colours | final")
    window = (slice(STAR[0] - half, STAR[0] + half), slice(STAR[1] - half, STAR[1] + half))
    mosaic = (raw[..., None] * BAYER)[window]
    crops = [mosaic / mosaic.max(), np.ones((2 * half, 2, 3)), final[window]]  # raw crop stretched for visibility
    return np.concatenate(crops, 1).repeat(factor, 0).repeat(factor, 1)


def ramp_profile(final):
    rgb, x = final[RAMP].mean(0), np.linspace(0, 1, WIDTH)
    curves = [[x, rgb[:, c], "rgb"[c], "RGB"[c]] for c in range(3)] + [[x, 0.95 ** (1 / 2.2) * x, "k:", "gamma 2.2"]]
    title = f"Grey ramp after the pipeline: R, G, B should overlap (mean spread {np.ptp(rgb, 1).mean():.3f})"
    return Curve(curves, title=title, xlabel="position along the ramp", ylabel="output value", grid=True)


@interactive_pipeline(gui="auto", cache="graph", name="Camera ISP")
def camera_isp():
    reflectance = scene()
    raw = sensor(reflectance)
    raw_view = show_raw(raw)
    linear, offset = subtract_black_level(raw)
    demosaiced = demosaic(linear)
    balanced, late_gains = white_balance(demosaiced, offset)
    final = gamma_encode(balanced, late_gains)
    detail = zoom(raw, final)
    grey_ramp = ramp_profile(final)
    return [[raw_view, demosaiced, detail], [balanced, final, grey_ramp]]


if __name__ == "__main__":
    camera_isp()
