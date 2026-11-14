"""A minimal camera pipeline (ISP): raw Bayer mosaic -> black level -> demosaic -> white balance -> gamma.

The sensor adds a constant offset (black level) and sees the scene through one
colour filter per photosite (RGGB). Every stage up to white balance is linear, and
white balance multiplies: it must scale light only, not the sensor offset, and not
gamma-encoded values. Get the black level or the stage order wrong and the grey
ramp at the bottom stops being grey: the curve runs the ramp through all three orders.
"""

import numpy as np

from interactive_pipe import Curve, Panel, interactive, interactive_pipeline, layout

HEIGHT, WIDTH, WHITE_LEVEL, SENSOR_BLACK = 256, 384, 1023, 64  # 10-bit sensor, values in DN
TUNGSTEN = np.array([1 / 1.6, 1.0, 1 / 2.5])  # raw response to white: the right gains are R x1.6, B x2.5
CHECKER = np.float64(  # ColorChecker patches, 8-bit sRGB, 4 rows of 6
    "115 82 68 194 150 130 98 122 157 87 108 67 133 128 177 103 189 170 214 126 44 80 91 166 193 90 99 94 60 108 "
    "157 188 64 224 163 46 56 61 150 70 148 73 175 54 60 231 199 31 187 86 149 8 133 161 243 243 242 200 200 200 "
    "160 160 160 122 122 121 85 85 85 52 52 52".split()
).reshape(4, 6, 3)
BAYER = np.zeros((HEIGHT, WIDTH, 3))  # which colour each photosite sees: RGGB
BAYER[::2, ::2, 0] = BAYER[::2, 1::2, 1] = BAYER[1::2, ::2, 1] = BAYER[1::2, 1::2, 2] = 1
RAMP, STAR = slice(196, 244), (88, 326)  # rows of the grey ramp, centre of the Siemens star
ORDERS = ["after black level (correct)", "before black level", "after gamma"]
STAGES = [Panel(name) for name in ("1. Black level", "2. Demosaic", "3. White balance", "4. Gamma")]
Panel(position="right").add_elements(STAGES)  # one column next to the images, in pipeline order


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
    layout.style("raw", title=f"Raw mosaic (RGGB), black at {SENSOR_BLACK} DN")
    return np.clip(np.round(noisy + SENSOR_BLACK), 0, WHITE_LEVEL) / WHITE_LEVEL  # stored as a fraction of white


@interactive(black_level=(SENSOR_BLACK, [0, 128], "black level to subtract (DN)", STAGES[0]))
def subtract_black_level(raw, black_level=SENSOR_BLACK):
    # no clipping: the noise in the dark stays unbiased. `offset` is the black level in the new units.
    level = black_level / WHITE_LEVEL
    return (raw - level) / (1 - level), level / (1 - level)


@interactive(method=("bilinear", ["bilinear", "half resolution"], "demosaic method", STAGES[1]))
def demosaic(mosaic, method="bilinear"):
    layout.style("demosaiced", title=f"Demosaiced ({method}), tungsten cast")
    if method == "half resolution":  # one RGB pixel per 2x2 block, although R, G and B were not seen at the same spot
        rgb = np.stack([mosaic[::2, ::2], (mosaic[::2, 1::2] + mosaic[1::2, ::2]) / 2, mosaic[1::2, 1::2]], -1)
        return rgb.repeat(2, 0).repeat(2, 1)
    # bilinear: a missing sample is the average of its nearest neighbours of the same colour
    rb = np.outer([1, 2, 1], [1, 2, 1]) / 4
    kernels = np.stack([rb, np.array([[0, 1, 0], [1, 4, 1], [0, 1, 0]]) / 4, rb], -1)  # (3, 3, channel): R, G, B
    padded = np.pad(mosaic[..., None] * BAYER, ((1, 1), (1, 1), (0, 0)), mode="reflect")  # keeps the Bayer phase
    return sum(kernels[i, j] * padded[i : i + HEIGHT, j : j + WIDTH] for i in range(3) for j in range(3))


def balance(rgb, offset, gains, order):
    """-> (balanced, gains left to apply after gamma)."""
    # before black level: the gains also multiply the offset, which is then subtracted as if unchanged
    leftover = (gains - 1) * offset if order == ORDERS[1] else 0
    return (rgb, gains) if order == ORDERS[2] else (gains * rgb + leftover, np.ones(3))


@interactive(
    red_gain=(1.6, [0.5, 4.0], "red gain", STAGES[2]),
    blue_gain=(2.5, [0.5, 4.0], "blue gain", STAGES[2]),
    grey_world=(False, "auto (grey world)", STAGES[2]),
    order=(ORDERS[0], ORDERS, "apply white balance", STAGES[2]),
)
def white_balance(rgb, offset, red_gain=1.6, blue_gain=2.5, grey_world=False, order=ORDERS[0]):
    """Balances the image with the chosen order, and the grey ramp with all three orders for comparison."""
    means = rgb.reshape(-1, 3).mean(0)
    gains = means[1] / means if grey_world else np.array([red_gain, 1.0, blue_gain])
    title = "Not balanced yet" if order == ORDERS[2] else "White balanced (linear)"
    layout.style("balanced", title=f"{title}: R x{gains[0]:.2f} B x{gains[2]:.2f}")
    ramps = [balance(rgb[RAMP].mean(0), offset, gains, each) for each in ORDERS]
    return *balance(rgb, offset, gains, order), ramps


@interactive(gamma=(2.2, [1.0, 3.0], "gamma", STAGES[3]))
def gamma_encode(balanced, late_gains, ramps, gamma=2.2):
    """Encodes the image and the three grey ramps; gains left for after gamma are applied last."""
    layout.style("final", title=f"Final: x^(1/{gamma:.1f}) brightens the shadows")
    finals = [np.clip(late * np.clip(img, 0, 1) ** (1 / gamma), 0, 1) for img, late in [(balanced, late_gains), *ramps]]
    return finals[0], finals[1:]


def zoom(raw, final, half=24, factor=4):
    layout.style("detail", title=f"Star centre x{factor}: raw mosaic | final")
    window = (slice(STAR[0] - half, STAR[0] + half), slice(STAR[1] - half, STAR[1] + half))
    mosaic = (raw[..., None] * BAYER)[window]
    crops = [mosaic / mosaic.max(), np.ones((2 * half, 2, 3)), final[window]]  # raw crop stretched for visibility
    return np.concatenate(crops, 1).repeat(factor, 0).repeat(factor, 1)


def ramp_error(final_ramps):
    layout.style("grey_ramp", title="Grey ramp colour error, per white balance order")
    spreads = [np.ptp(ramp, 1) for ramp in final_ramps]  # max - min of R, G, B: 0 when grey
    x, names = np.linspace(0, 1, WIDTH), ["WB after black level", "WB before black level", "WB after gamma"]
    curves = [[x, spread, f"C{k}-", f"{names[k]}: {spread.mean():.3f}"] for k, spread in enumerate(spreads)]
    return Curve(curves, xlabel="position along the ramp", ylabel="max - min of R, G, B", grid=True, ylim=(0, 1))


@interactive_pipeline(gui="auto", cache="graph", name="Camera ISP")
def camera_isp():
    reflectance = scene()
    raw = sensor(reflectance)
    linear, offset = subtract_black_level(raw)
    demosaiced = demosaic(linear)
    balanced, late_gains, ramps = white_balance(demosaiced, offset)
    final, final_ramps = gamma_encode(balanced, late_gains, ramps)
    detail = zoom(raw, final)
    grey_ramp = ramp_error(final_ramps)
    return [[raw, demosaiced, detail], [balanced, final, grey_ramp]]


if __name__ == "__main__":
    camera_isp()
