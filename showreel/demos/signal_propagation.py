"""Signal propagation at initialization in a 50-layer MLP of constant width n (PyTorch, CPU).

Each layer computes h_l = f(z_l), z_l = W_l h_{l-1}, with weights of variance gain^2 / n:
    Var(z_l) = gain^2 * E[h_{l-1}^2]
so the signal is multiplied by about the same factor at every layer and, after 50 layers,
anything but 1 vanishes or explodes geometrically.
- linear: factor = gain. Xavier/Glorot (gain 1) is exact.
- relu: zeroes half the units, E[h^2] = Var(z) / 2, factor = gain / sqrt(2). Xavier shrinks the
  std by 0.71 per layer (2^-25 ~ 3e-8 after 50 layers); He/Kaiming (gain sqrt 2) keeps it flat.
- tanh: tanh'(0) = 1, so gain 1 only decays slowly (std ~ 1/sqrt(2 l), not geometrically).
  Gain 2 saturates the units at +-1 (histogram edges): the forward std looks fine, but the
  backward pass becomes chaotic and gradients grow towards the input.
The backward pass multiplies by W^T and f'(z): gradients follow the same factor, from the
output down to the input. LayerNorm rescales every layer: the forward std is flat for any gain.
Default: relu + Xavier, the signal dies. Switch the initialization to He.
The histograms divide each layer by its std: they show the shape (spike at 0 for relu,
saturation for tanh), the curves show the scale.
"""

import numpy as np
import torch

from interactive_pipe import Curve, interactive, interactive_pipeline, layout

torch.set_num_threads(1)  # small matrices: threading overhead costs more than it brings
WIDTH, BATCH, LOG_RANGE, HIST_RANGE, BINS = 128, 256, 12, 4.0, 61
ACTIVATIONS = {"relu": torch.relu, "tanh": torch.tanh, "gelu": torch.nn.functional.gelu, "linear": lambda z: z}
INITS = {"Xavier (gain 1)": torch.nn.init.xavier_normal_, "He (gain √2)": torch.nn.init.kaiming_normal_}


@interactive(
    init=("Xavier (gain 1)", list(INITS), "initialization"),
    gain=(1.0, [0.5, 2.0], "gain multiplier"),
    depth=(50, [5, 100], "depth"),
)
def initialize(init="Xavier (gain 1)", gain=1.0, depth=50):
    generator = torch.Generator().manual_seed(0)
    # constant width: Xavier std = sqrt(2 / (fan_in + fan_out)) = 1 / sqrt(n), He std = sqrt(2 / n)
    return gain * torch.stack([INITS[init](torch.empty(WIDTH, WIDTH), generator=generator) for _ in range(depth)])


@interactive(
    activation=("relu", list(ACTIVATIONS), "activation"),
    normalize=(False, "LayerNorm before each activation"),
)
def forward(weights, activation="relu", normalize=False):
    x = torch.randn(BATCH, WIDTH, generator=torch.Generator().manual_seed(1))  # unit-variance inputs
    layers = [x.requires_grad_()]
    for w in weights:
        z = layers[-1] @ w.T
        z = torch.nn.functional.layer_norm(z, (WIDTH,)) if normalize else z
        layers.append(ACTIVATIONS[activation](z))
    return {"layers": layers}


def backward(signals):  # gradient of a random scalar read-out of the last layer, w.r.t. every layer
    layers = signals["layers"]
    loss = layers[-1] @ torch.randn(WIDTH, generator=torch.Generator().manual_seed(2))
    return torch.stack(torch.autograd.grad(loss.sum(), layers, retain_graph=True))


def log_std_plot(std, title, ylabel, reference):
    depth = len(std) - 1
    log_std = np.clip(np.log10(std + 1e-30), -LOG_RANGE, LOG_RANGE)
    curves = [[np.arange(depth + 1), log_std, "b-o", ylabel], [[0, depth], [0, 0], "k--", reference]]
    ylim = (-LOG_RANGE, LOG_RANGE)
    return Curve(curves, xlabel="layer (0 = input)", ylabel=f"log10 {ylabel}", title=title, ylim=ylim, grid=True)


def plot_std(signals, gradients):  # titles: geometric mean of the factor per layer
    act = np.array([h.std().item() for h in signals["layers"]])
    grad = gradients.flatten(1).std(1).numpy()
    n = len(act) - 1
    forward_title = f"Forward: activation std x{(act[-1] / act[0]) ** (1 / n):.3f} per layer"
    backward_title = f"Backward: gradient std x{(grad[0] / grad[-1]) ** (1 / n):.3f} per layer, to the input"
    return (
        log_std_plot(act, forward_title, "activation std", "input std (1)"),
        log_std_plot(grad, backward_title, "gradient std", "output gradient std (1)"),
    )


def histograms(signals):  # one row per layer: the shape of the activations, their scale divided out
    layers = torch.stack([h / h.std() for h in signals["layers"]]).detach().clamp(-HIST_RANGE, HIST_RANGE)
    img = torch.stack([torch.histc(h, BINS, -HIST_RANGE, HIST_RANGE) for h in layers]).numpy()
    img = np.sqrt(img / img.max(axis=1, keepdims=True))  # sqrt: show the tails next to the peak
    layout.style(
        "saturation", title=f"Histograms of activation / std, layer 0 (top) to {len(img) - 1}, range ±{HIST_RANGE:g}"
    )
    return np.repeat(np.repeat(1 - img, 300 // len(img) + 1, axis=0), 5, axis=1)


@interactive_pipeline()
def signal_propagation():
    weights = initialize()
    signals = forward(weights)
    gradients = backward(signals)
    activation_std, gradient_std = plot_std(signals, gradients)
    saturation = histograms(signals)
    return [activation_std, gradient_std, saturation]


if __name__ == "__main__":
    signal_propagation()
