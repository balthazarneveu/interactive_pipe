# Volume rendering along one ray, NeRF quadrature with N samples t_i, each owning a bin of length delta:
#   alpha_i = 1 - exp(-sigma_i delta)        opacity of bin i
#   T_i     = prod_{j<i} (1 - alpha_j)       light that survives up to sample i
#   w_i     = T_i alpha_i                    share of the pixel given to sample i (sum w_i = 1 - T_N)
#   colour  = sum w_i c_i + T_N background,  expected depth = sum w_i t_i / sum w_i
import numpy as np

from interactive_pipe import Curve, Panel, interactive, interactive_pipeline, layout

NEAR, FAR, FINE_SAMPLES = 0.0, 10.0, 20000
COLOURS, BACKGROUND = np.array([[1.0, 0.4, 0.1], [0.1, 0.4, 1.0]]), np.ones(3)  # front orange, back blue
# controls on the right: below the plots, the eight sliders would not fit and would scroll
front, back, sampling = (Panel(name, position="right") for name in ("Front surface", "Back surface", "Sampling"))


def march(scene, n, offset):  # n samples, each placed at `offset` inside its bin of length delta
    delta = (FAR - NEAR) / n
    t = NEAR + (np.arange(n) + offset) * delta
    pos, width, dens = scene[:, :1], scene[:, 1:2], scene[:, 2:]
    each = dens * np.exp(-0.5 * ((t - pos) / width) ** 2)  # (surface, sample): Gaussian density bumps
    sigma = each.sum(0)
    rgb = each.T @ COLOURS / np.maximum(sigma, 1e-12)[:, None]  # density-weighted colour mix
    alpha = 1.0 - np.exp(-sigma * delta)
    trans = np.cumprod(np.append(1.0, 1.0 - alpha))  # T_0 .. T_N
    w = trans[:-1] * alpha
    depth = w @ t / w.sum() if w.sum() > 1e-6 else np.nan
    return dict(t=t, delta=delta, sigma=sigma, trans=trans, w=w, colour=w @ rgb + trans[-1] * BACKGROUND, depth=depth)


@interactive()
def build_scene(
    front_position=(3.1, [1.0, 9.0], "front position", front),
    front_width=(0.08, [0.02, 1.0], "front width", front),
    front_density=(30.0, [0.0, 50.0], "front density", front),
    back_position=(5.0, [1.0, 9.0], "back position", back),
    back_width=(0.5, [0.02, 1.0], "back width", back),
    back_density=(8.0, [0.0, 50.0], "back density", back),
):
    return np.array([[front_position, front_width, front_density], [back_position, back_width, back_density]])


@interactive()
def render(scene, n_samples=(16, [2, 128], "samples N", sampling), offset=(0.5, [0.0, 1.0], "offset in bin", sampling)):
    return march(scene, n_samples, offset), march(scene, FINE_SAMPLES, 0.5)


def stems(x, y):  # vertical bars as one polyline broken by NaNs
    return np.stack([x, x, np.nan * x], 1).ravel(), np.stack([0 * y, y, np.nan * y], 1).ravel()


def plot(ylabel, ylim, *curves):
    return Curve(curves, xlabel="t along the ray", ylabel=ylabel, xlim=(NEAR, FAR), ylim=ylim, grid=True)


def plot_ray(smp, ref):
    n, t, t_fine = len(smp["t"]), smp["t"], ref["t"]
    fine, samples = dict(style="k-", label="fine grid"), dict(style="ro", label=f"{n} samples")
    density = plot("σ", (0, 1.1 * ref["sigma"].max() + 1e-3), [t_fine, ref["sigma"], fine], [t, smp["sigma"], samples])
    transmittance = plot("T", (0, 1.4), [t_fine, ref["trans"][:-1], fine], [t, smp["trans"][:-1], samples])
    # the weight each bin should get: fine-grid weights summed over the bin
    per_bin = np.bincount(((t_fine - NEAR) // smp["delta"]).astype(int), ref["w"], n)
    bin_centres = NEAR + (np.arange(n) + 0.5) * smp["delta"]
    weights = plot(
        "w",
        (0, 1.4),  # headroom above 1 for the legend
        [*stems(bin_centres, per_bin), dict(style="k-", linewidth=8, alpha=0.25, label="fine grid, per bin")],
        [*stems(t, smp["w"]), dict(style="r-", linewidth=2, label=f"{n} samples")],
        [[ref["depth"]] * 2, [0, 1.05], "k--"],  # expected depths, drawn as vertical lines
        [[smp["depth"]] * 2, [0, 1.05], "r:"],
    )
    swatch = np.ones((60, 130, 3))
    swatch[:, :60], swatch[:, 70:] = smp["colour"], ref["colour"]
    layout.style("density", title="Density σ along the ray")
    layout.style("transmittance", title=f"Transmittance T: {smp['trans'][-1]:.2f} of the light gets through")
    layout.style("weights", title=f"Weights w = T α, depth {smp['depth']:.2f} (fine grid {ref['depth']:.2f})")
    layout.style("swatch", title=f"Pixel colour: {n} samples | fine grid")
    return density, transmittance, weights, np.clip(swatch, 0, 1)


@interactive_pipeline(cache="graph", name="Volume rendering along a ray")
def volume_rendering():
    scene = build_scene()
    sampled, reference = render(scene)
    density, transmittance, weights, swatch = plot_ray(sampled, reference)
    return [[density, transmittance], [weights, swatch]]


if __name__ == "__main__":
    volume_rendering()
