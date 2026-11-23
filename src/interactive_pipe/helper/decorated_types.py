"""Static types of what ``@interactive`` and ``@interactive_pipeline`` return.

Both decorators return plain functions with a few attributes attached at
runtime (``amplify.snapshot``, ``demo.headless``...). These protocols describe
those objects to type checkers (mypy, pyright), so that user code stays
fully typed under ``--strict``:

- ``InteractiveFilter[P, R]`` keeps the filter's own signature: calling
  ``amplify(img, gain=2.0)`` is checked against ``def amplify(img, gain=1.0)``
  and returns what ``amplify`` returns.
- ``PipelineApp`` is the decorated pipeline function (with a window or not).
  ``HeadlessPipeline`` satisfies it as well.

They only exist for typing: nothing checks them at runtime.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, TypeVar, Union

import numpy as np

if sys.version_info >= (3, 10):
    from typing import ParamSpec, Protocol
else:  # Generic[ParamSpec] needs typing_extensions' Protocol before 3.10
    from typing_extensions import ParamSpec, Protocol

if TYPE_CHECKING:
    from interactive_pipe.graphical.gui import InteractivePipeGUI
    from interactive_pipe.headless.pipeline import HeadlessPipeline

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)
T_co = TypeVar("T_co", covariant=True)

#: what ``snapshot`` / ``sweep`` return: the written path, or the picture when path is None
SnapshotResult = Union[Path, np.ndarray]


class InteractiveFilter(Protocol[P, R_co]):
    """A function decorated with ``@interactive``: same call signature and
    return type as the original, plus the single-filter entry points."""

    __name__: str
    __doc__: Optional[str]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...

    def snapshot(
        self, path: Any, *input_values: Any, inputs: Optional[Dict[str, Any]] = None, **options: Any
    ) -> SnapshotResult: ...

    def sweep(
        self, path: Any, *input_values: Any, inputs: Optional[Dict[str, Any]] = None, **options: Any
    ) -> SnapshotResult: ...

    def describe(self, *input_values: Any, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...

    def summary(self, *input_values: Any, inputs: Optional[Dict[str, Any]] = None) -> str: ...

    def interact(self, *input_values: Any, gui: Any = "auto", **gui_kwargs: Any) -> Any: ...


class PipelineApp(Protocol):
    """A function decorated with ``@interactive_pipeline``.

    Calling it runs the pipeline on its inputs (opening the window unless
    ``gui=None``); keyword arguments set parameters (``demo(img, gain=2.0)``).
    """

    @property
    def headless(self) -> "HeadlessPipeline": ...

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...

    def snapshot(self, path: Any, *input_values: Any, **options: Any) -> SnapshotResult: ...

    def sweep(self, path: Any, *input_values: Any, **options: Any) -> SnapshotResult: ...

    def describe(self) -> Dict[str, Any]: ...

    def summary(self) -> str: ...

    def graph_representation(
        self, path: Any = None, ortho: bool = True, view: bool = False, format: Optional[str] = None
    ) -> Any: ...


class GuiPipelineApp(PipelineApp, Protocol):
    """``@interactive_pipeline(gui=...)`` with a window: ``.pipeline`` is the GUI
    object, e.g. ``demo.pipeline.bind_key_to_context(...)``."""

    @property
    def pipeline(self) -> "InteractivePipeGUI": ...


class PipelineDecorator(Protocol[T_co]):
    """What ``interactive_pipeline(...)`` returns: applied to a pipeline function,
    it gives a ``HeadlessPipeline`` or a ``GuiPipelineApp``.

    A protocol rather than a plain ``Callable`` so that a ``gui`` typed ``Any``
    (e.g. from argparse) still gives a typed call under ``mypy --strict``."""

    def __call__(self, pipeline_function: Callable[..., Any], /) -> T_co: ...
