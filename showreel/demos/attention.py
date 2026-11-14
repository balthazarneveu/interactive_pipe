"""Scaled dot-product attention under the microscope.

Each token is a vector x = (1 - w) content + w position, rescaled to norm sqrt(d). With no learned
projections (queries = keys = x), the attention matrix is
    A = softmax(x x^T / (sqrt(d) temperature))       (row i: how much token i reads each token j)
and every token matches itself best: the diagonal is always bright.
- by content (w = 0), a query lights up every occurrence of its own word;
- by position (w = 1, sinusoidal), it reads its neighbours: a band around the diagonal;
- temperature -> 0 gives one-hot rows (argmax), temperature -> infinity uniform rows;
- the causal mask forbids reading the future: the upper triangle is exactly 0, rows still sum to 1.
Step the query token with the left / right arrow keys.
"""

import numpy as np
from matplotlib import colormaps

from interactive_pipe import Curve, KeyboardControl, context, interactive, interactive_pipeline, layout

TOKENS = "the cat sat on the mat the dog sat on the cat".split()
VOCABULARY = sorted(set(TOKENS))
N, D, CELL = len(TOKENS), 32, 32  # sequence length, embedding size, heatmap pixels per token


def unit(v):  # norm sqrt(D) for every vector, so that x x^T / sqrt(D) = sqrt(D) cos(angle)
    return np.sqrt(D) * v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def positional_encodings(kind):
    position, rng = np.arange(N)[:, None], np.random.default_rng(1)
    frequencies = 100.0 ** (-np.arange(0, D, 2) / D)  # base 100 instead of 10000: suits a 12-token sequence
    return {
        "sinusoidal": unit(np.concatenate([np.sin(position * frequencies), np.cos(position * frequencies)], 1)),
        "learned (random)": unit(rng.normal(size=(N, D))),  # an untrained table: no notion of neighbourhood
        "none": np.zeros((N, D)),
    }[kind]


@interactive(
    position_weight=(0.25, [0.0, 1.0], "position weight (0 = content, 1 = position)"),
    kind=("sinusoidal", ["sinusoidal", "learned (random)", "none"], "positional encoding"),
)
def embed(position_weight=0.25, kind="sinusoidal"):
    content = unit(np.random.default_rng(0).normal(size=(len(VOCABULARY), D)))  # one fixed vector per word
    content = content[[VOCABULARY.index(token) for token in TOKENS]]
    position = positional_encodings(kind)
    return unit((1 - position_weight) * content + position_weight * position), position


@interactive(
    log_temperature=(-0.5, [-2.0, 2.0], "temperature, log10 scale (-1 = 0.1, 0 = 1)"), causal=(False, "causal mask")
)
def attention(x, log_temperature=-0.5, causal=False):
    temperature = 10.0**log_temperature
    layout.style("attention_map", title=f"Attention A[query, key], temperature {temperature:.2g}")
    scores = x @ x.T / (np.sqrt(D) * temperature)
    if causal:
        scores[np.triu_indices(N, 1)] = -np.inf  # exp(-inf) = 0 exactly: the future gets no weight
    context["visible_keys"] = np.arange(1, N + 1) if causal else np.full(N, N)  # for the entropy of a uniform row
    weights = np.exp(scores - scores.max(1, keepdims=True))  # subtract the row max: no overflow at low temperature
    return weights / weights.sum(1, keepdims=True)


def heatmap(matrix, low=0.0, high=1.0):  # one CELL x CELL square per entry, magma colours
    rgb = colormaps["magma"](np.clip((matrix - low) / (high - low), 0, 1))[..., :3]
    return np.repeat(np.repeat(rgb, CELL, 0), CELL, 1)


@interactive(query=KeyboardControl(6, [0, N - 1], keydown="left", keyup="right", modulo=True, name="query token"))
def show_query(weights, query=6):
    image = heatmap(weights)
    top, bottom = query * CELL, (query + 1) * CELL - 1
    image[[top, top + 1, bottom - 1, bottom], :] = image[top:bottom, [0, 1, -2, -1]] = [0.2, 0.9, 1.0]  # cyan frame
    row = weights[query]
    entropy, visible = -(row[row > 0] * np.log2(row[row > 0])).sum(), context["visible_keys"][query]
    bars_x = (np.arange(N)[:, None] + [-0.4, -0.4, 0.4, 0.4, np.nan]).ravel()  # one rectangle outline per key
    bars_y = (row[:, None] * [0, 1, 1, 0, np.nan]).ravel()
    layout.style("attention_row", title=f"row {query} of A: attention weights of '{TOKENS[query]}'")
    return image, Curve(
        [
            [bars_x, bars_y, dict(style="-", linewidth=3, label=f"query {query} '{TOKENS[query]}'")],
            [[-0.5, N - 0.5], [1 / visible] * 2, "k--", f"uniform: 1/{visible}"],
        ],
        title=f"entropy {entropy:.2f} bits (uniform: {np.log2(visible):.2f})",
        xlabel=" ".join(TOKENS),  # key j is the j-th word; no ylabel: it would push this one off the plot
        xlim=(-0.5, N - 0.5),
        ylim=(0, 1.05),
        grid=True,
    )


def position_similarity(position):
    layout.style("similarity", title="cos(position i, position j): -1 black, 1 yellow")
    return heatmap(position @ position.T / D, low=-1.0)


@interactive_pipeline(name="Attention", cache="graph")
def attention_demo():
    x, position = embed()
    weights = attention(x)
    attention_map, attention_row = show_query(weights)
    similarity = position_similarity(position)
    return [attention_map, attention_row, similarity]


if __name__ == "__main__":
    attention_demo()
