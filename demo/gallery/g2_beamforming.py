"""Antenna arrays: array factor of a uniform linear array steered by phase shifts.

What to look at: the main lobe narrows as the number of elements grows (beamwidth ~ 1 / (N d)).
Spacing above half a wavelength brings grating lobes (copies of the main lobe) into visible
space: the heatmap of the array factor versus spacing shows where they appear, sooner when the
beam is steered off broadside. A Hann taper lowers the side lobes (-13 dB to -31 dB) at the cost of
a wider main lobe.
"""

from typing import Annotated, Tuple, cast

import numpy as np
from matplotlib.figure import Figure
from matplotlib.projections.polar import PolarAxes

from interactive_pipe import Control, interactive, interactive_pipeline, layout

ANGLES = np.linspace(-90, 90, 361)  # degrees from broadside
SPACINGS = np.linspace(0.1, 2.0, 120)  # in wavelengths
# one slider each, shared by both filters
ELEMENTS = Control(8, [2, 32], name="elements")
STEERING = Control(20.0, [-60.0, 60.0], name="steering (deg)")
TAPER = Control("uniform", ["uniform", "hann"], name="taper")


def array_factor_db(n: int, spacing: float, steering: float, taper: str, angles: np.ndarray = ANGLES) -> np.ndarray:
    weights = np.hanning(n + 2)[1:-1] if taper == "hann" else np.ones(n)
    phase = 2 * np.pi * spacing * (np.sin(np.radians(angles))[..., None] - np.sin(np.radians(steering)))
    response = np.abs(np.exp(1j * phase * np.arange(n)) @ weights) / weights.sum()
    gain_db: np.ndarray = 20 * np.log10(np.maximum(response, 1e-5))
    return gain_db


@interactive(elements=ELEMENTS, steering=STEERING, taper=TAPER)
def pattern(
    elements: int = 8,
    spacing: Annotated[float, (0.1, 2.0), "spacing (wavelengths)"] = 0.5,
    steering: float = 20.0,
    taper: str = "uniform",
) -> PolarAxes:
    gain = array_factor_db(elements, spacing, steering, taper)
    lo = hi = int(np.argmin(np.abs(ANGLES - steering)))  # main lobe: walk down to the nulls around the peak
    while lo > 0 and gain[lo - 1] < gain[lo]:
        lo -= 1
    while hi < len(gain) - 1 and gain[hi + 1] < gain[hi]:
        hi += 1
    side = max(gain[:lo].max(initial=-100), gain[hi + 1 :].max(initial=-100))
    width = np.ptp(ANGLES[lo:hi][gain[lo:hi] > -3])
    layout.style("polar", title=f"-3 dB width {width:.1f} deg, highest side lobe {side:.1f} dB")
    ax = cast(PolarAxes, Figure(figsize=(4, 3)).add_subplot(projection="polar"))
    ax.plot(np.radians(ANGLES), np.maximum(gain, -40) + 40, "b-")
    ax.set_thetalim(-np.pi / 2, np.pi / 2)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(-90)
    ax.set_yticks([10, 20, 30, 40], ["-30", "-20", "-10", "0 dB"])
    return ax


@interactive(elements=ELEMENTS, steering=STEERING, taper=TAPER)
def spacing_map(elements: int = 8, steering: float = 20.0, taper: str = "uniform") -> np.ndarray:
    rows = [array_factor_db(elements, d, steering, taper, angles=np.arange(-90, 91)) for d in SPACINGS]
    layout.style("spacing_vs_angle", title="array factor vs spacing", colormap="magma", vmin=-40, vmax=0)
    # rows run from 0.1 (top) to 2 wavelengths (bottom): extent = (left, right, bottom, top)
    axes = dict(extent=(-90, 90, 2.0, 0.1), xlabel="angle (deg)", ylabel="spacing (wavelengths)")
    layout.style("spacing_vs_angle", colorbar="array factor (dB)", **axes)
    return np.array(rows)


@interactive_pipeline(gui="auto")
def g2_beamforming() -> Tuple[PolarAxes, np.ndarray]:
    polar = pattern()
    spacing_vs_angle = spacing_map()
    return polar, spacing_vs_angle


if __name__ == "__main__":
    g2_beamforming()
