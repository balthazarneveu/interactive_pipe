"""Typed user code that must stay clean under ``mypy --strict`` and pyright strict.

Never executed: ``test/test_static_typing.py`` runs the type checkers on it.
``assert_type`` lines fail the check when a decorator loses the filter's types.
"""

from typing import Any, List, Tuple

import numpy as np
from numpy.typing import NDArray
from typing_extensions import Annotated, assert_type

import interactive_pipe as ip
from interactive_pipe import Control, Curve, HeadlessPipeline, Table, context, interactive, interactive_pipeline, layout

Array = NDArray[np.float64]


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img: Array, gain: float = 1.0) -> Array:
    layout.style("amplify", title="Amplified")
    context["gain"] = gain
    return img * gain


@interactive
def flip(img: Array) -> Array:
    return img[::-1]


@interactive()
def annotated(
    img: Array,
    strength: Annotated[float, (0.0, 3.0)] = 1.0,
    mode: Annotated[str, Control("a", ["a", "b"])] = "a",
) -> Array:
    return img * strength


@ip.block(inplace=True)
def split(img: Array) -> Tuple[Array, Array]:
    return img, img


@interactive()
def profile(img: Array) -> Curve:
    return Curve([(np.arange(4), img[0, :4], "row")], title="profile")


@interactive()
def stats(img: Array) -> Table:
    return Table({"mean": [float(img.mean())], "max": [float(img.max())]})


@interactive_pipeline(gui="qt")
def app(img: Array) -> List[Any]:
    left, right = split(img)
    out = amplify(flip(left), gain=2.0)
    return [out, annotated(right), profile(out), stats(out)]


@interactive_pipeline(gui=None)
def batch(img: Array) -> List[Array]:
    return [amplify(img)]


@ip.pipeline()
def default_gui(img: Array) -> List[Array]:
    return [amplify(img)]


def checks() -> None:
    img = np.zeros((4, 4))
    assert_type(amplify(img), Array)
    assert_type(amplify(img, gain=2.0), Array)
    assert_type(split(img), Tuple[Array, Array])
    assert_type(batch, HeadlessPipeline)
    app.pipeline.bind_key_to_context("k", "toggle", "toggle something")
    outputs: Any = batch(img, gain=2.0)
    print(outputs, app.headless(img), default_gui.summary(), amplify.summary(), amplify.__name__)
    app.snapshot("app.png", img, gain=2.0)
    app.sweep("sweep.png", img, gain=[0.5, 1.0, 2.0])
    amplify.snapshot("amplify.png", img)
