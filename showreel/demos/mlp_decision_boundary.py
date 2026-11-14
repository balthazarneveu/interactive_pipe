"""Capacity vs regularization: a small MLP (PyTorch, CPU) learns a 2D decision boundary."""

# Under-fit: width 2 / 1 hidden layer, or 10 steps -> a nearly straight boundary, both losses high.
# Over-fit: just set weight decay to 0, or go to noise 0.35, 40 points, width 64, 3 layers, 600 steps:
# the boundary wraps around single noisy points, the training loss -> 0 while the validation loss
# climbs (the net grows over-confident). Weight decay pulls it back.
# cache="graph" recomputes only the filters downstream of a change: display controls never
# retrain, network controls never resample the dataset.

import numpy as np
import torch

from interactive_pipe import Curve, Panel, interactive, interactive_pipeline, layout

torch.set_num_threads(1)  # tiny matrices: threading overhead costs more than it brings
BLUE, ORANGE, EXTENT, CANVAS, PAD = np.array([0.15, 0.35, 0.85]), np.array([0.95, 0.5, 0.05]), 2.0, 400, 10
# Data and Network side by side, Display folded away: the plots stay above the fold
DATA, NETWORK, DISPLAY = Panel("Data"), Panel("Network"), Panel("Display", collapsible=True, collapsed=True)
Panel().add_elements([[DATA, NETWORK]])


def sample(kind, n, noise, rng):
    label = rng.integers(0, 2, n)
    if kind == "moons":
        t = rng.uniform(0, np.pi, n)  # class 1 is class 0 flipped and shifted: interlocking crescents
        x = (1 - 2 * label[:, None]) * np.stack([np.cos(t), np.sin(t)], 1) + label[:, None] * [1, 0.5] - [0.5, 0.25]
    else:  # two interleaved spirals
        t = np.sqrt(rng.uniform(0.02, 1, n)) * 3 * np.pi
        x = np.stack([np.cos(t + np.pi * label), np.sin(t + np.pi * label)], 1) * t[:, None] / (2 * np.pi)
    return torch.tensor(x + noise * rng.normal(size=x.shape), dtype=torch.float32), torch.tensor(label).float()


@interactive(
    kind=("moons", ["moons", "spirals"], "dataset", DATA),
    noise=(0.25, [0.0, 0.5], "noise", DATA),
    n_train=(100, [20, 300], "training points", DATA),
)
def make_dataset(kind="moons", noise=0.25, n_train=100):
    rng = np.random.default_rng(0)  # same points every time: only the slider values matter
    return {"train": sample(kind, n_train, noise, rng), "validation": sample(kind, 300, noise, rng)}


@interactive(
    width=(32, [2, 64], "width", NETWORK),
    depth=(2, [1, 4], "hidden layers", NETWORK),
    weight_decay=(0.01, [0.0, 0.03], "weight decay", NETWORK),
    steps=(300, [10, 600], "training steps", NETWORK),
)
def train(data, width=32, depth=2, weight_decay=0.01, steps=300):
    (x_train, y_train), (x_val, y_val) = data["train"], data["validation"]
    torch.manual_seed(0)
    layers = [m for i in range(depth) for m in (torch.nn.Linear(2 if i == 0 else width, width), torch.nn.ReLU())]
    net = torch.nn.Sequential(*layers, torch.nn.Linear(width, 1), torch.nn.Flatten(0))
    # full-batch Adam; weight_decay adds weight_decay * w to every gradient (an L2 penalty)
    optimizer = torch.optim.Adam(net.parameters(), lr=0.01, weight_decay=weight_decay)
    bce = torch.nn.functional.binary_cross_entropy_with_logits
    history = []
    for step in range(steps):
        loss = bce(net(x_train), y_train)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if step % 10 == 0 or step == steps - 1:  # the validation pass costs more than a step
            with torch.no_grad():
                history.append((step, loss.item(), bce(net(x_val), y_val).item()))
    step, train_loss, val_loss = np.array(history).T
    layout.style("losses", title="cross-entropy loss during training")
    title = f"train {train_loss[-1]:.3f} / validation {val_loss[-1]:.3f}"
    curves = [(step, train_loss, "b-", "train"), (step, val_loss, "r-", "validation")]
    net.requires_grad_(False)  # inference only from here: drawing builds no autograd graph
    return net, Curve(curves, xlabel="step", ylabel="cross-entropy", title=title, ylim=(0, 1), grid=True)


def stamp(img, points, colors, radius):  # one disc per point, on a canvas with a PAD-pixel margin
    col, row = ((points * [1, -1] + EXTENT) / (2 * EXTENT) * (CANVAS - 1)).round().astype(int).T + PAD
    disc = np.mgrid[-radius : radius + 1, -radius : radius + 1].reshape(2, -1).T
    for dy, dx in disc[np.hypot(*disc.T) <= radius]:  # radius < PAD: an index never leaves the canvas
        img[row + dy, col + dx] = colors


@interactive(
    resolution=(160, [10, 200], "grid resolution", DISPLAY),
    point_size=(4, [2, 8], "point size", DISPLAY),
    show_validation=(False, "show validation points", DISPLAY),
)
def draw_boundary(data, net, resolution=160, point_size=4, show_validation=False):
    axis = np.linspace(-EXTENT, EXTENT, resolution, dtype=np.float32)
    grid = torch.tensor(np.stack(np.meshgrid(axis, axis[::-1]), -1).reshape(-1, 2))
    prob = torch.sigmoid(net(grid)).numpy().reshape(resolution, resolution)
    prob = prob[np.ix_(*[np.arange(CANVAS) * resolution // CANVAS] * 2)]  # nearest-neighbour upsampling
    # tint = predicted class, strength = confidence |2p - 1|: an over-confident net paints everything
    side = prob > 0.5
    img = 1 - 0.5 * np.abs(2 * prob - 1)[..., None] * (1 - np.where(side[..., None], ORANGE, BLUE))
    img[np.diff(side, axis=0, prepend=side[:1]) | np.diff(side, axis=1, prepend=side[:, :1])] = 0.1  # boundary
    img = np.pad(img, ((PAD, PAD), (PAD, PAD), (0, 0)))
    # validation points (smaller, white outline) go under the training points (black outline)
    for name in ["validation", "train"][1 - show_validation :]:
        (x, y), small = [v.numpy() for v in data[name]], int(name == "validation")
        inside = (np.abs(x) <= EXTENT).all(1)  # drop the points off the plane
        x, y = x[inside], y[inside]
        stamp(img, x, float(small), point_size + 1 - small)
        stamp(img, x, np.where(y[:, None] > 0.5, ORANGE, BLUE), point_size - small)
    acc = {name: ((net(x) > 0).float() == y).float().mean().item() for name, (x, y) in data.items()}
    layout.style("boundary", title=f"accuracy: train {acc['train']:.0%} / validation {acc['validation']:.0%}")
    return img[PAD:-PAD, PAD:-PAD]


# with gui="qt", adding threaded=True keeps the sliders live while a long training runs
@interactive_pipeline(gui="auto", cache="graph")
def mlp_decision_boundary():
    data = make_dataset()
    net, losses = train(data)
    boundary = draw_boundary(data, net)
    return [boundary, losses]


if __name__ == "__main__":
    mlp_decision_boundary()
