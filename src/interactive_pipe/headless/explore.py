"""See-the-result loop for a pipeline: snapshot, sweep (and the helpers they share).

These functions take the pipeline as first argument and are exposed as
``HeadlessPipeline.snapshot`` / ``.sweep``; they are also reachable from a
GUI-decorated pipeline function (``my_pipeline.snapshot(...)``) and from a
single ``@interactive`` filter (``my_filter.snapshot(...)``).

Both are stateless with respect to tuning: the parameter overrides apply to
the call only, and the pipeline parameters, control values, output layout,
display styles and last results are restored afterwards, also when a run
raises.
"""

import difflib
import warnings
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np

from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.snapshot import (
    OutputSelector,
    figure_to_rgb,
    format_parameters,
    format_value,
    render_grid,
    result_grid,
    save_figure,
    select_cells,
)

if TYPE_CHECKING:
    from interactive_pipe.headless.pipeline import HeadlessPipeline

PathLike = Union[str, Path, None]
Target = Tuple[str, str]  # (filter name, parameter name)

#: ``output=`` value asking a sweep to show every output in each cell
ALL_OUTPUTS = "all"


# ---------------------------------------------------------------------------
# Parameter names
# ---------------------------------------------------------------------------


def _controls(pipeline: Any) -> List[Control]:
    return list(getattr(pipeline, "controls", None) or [])


def parameter_targets(pipeline: Any) -> Dict[str, List[Target]]:
    """Names accepted as parameter overrides and the filter parameters they set.

    - a keyword-argument name sets it in every filter that has it (like
      ``pipeline(img, gain=2)``);
    - a control name (``Control(..., name="exposure")``, or the ``gain_1``
      clone of a repeated filter) sets the parameter it drives;
    - ``"filter_name.parameter"`` sets one filter only.
    """
    targets: Dict[str, List[Target]] = {}
    for filt in pipeline.filters:
        for param_name in filt.values:
            targets.setdefault(param_name, []).append((filt.name, param_name))
            targets[f"{filt.name}.{param_name}"] = [(filt.name, param_name)]
    for ctrl in _controls(pipeline):
        if ctrl.filter_to_connect is None or ctrl.parameter_name_to_connect is None:
            continue
        targets.setdefault(ctrl.name, [(ctrl.filter_to_connect.name, ctrl.parameter_name_to_connect)])
    return targets


def resolve_names(pipeline: Any, names: Sequence[str], method: str = "snapshot") -> Dict[str, List[Target]]:
    """Map override names to filter parameters; unknown names raise TypeError
    listing the available ones (with a close match when there is one)."""
    targets = parameter_targets(pipeline)
    resolved = {}
    for name in names:
        if name in targets:
            resolved[name] = targets[name]
            continue
        available = sorted(key for key in targets if "." not in key)
        close = difflib.get_close_matches(name, list(targets), n=1)
        hint = f" Did you mean {close[0]!r}?" if close else ""
        raise TypeError(
            f"{method}() got an unknown parameter {name!r}.{hint} "
            f"Available parameters: {', '.join(available) or '(none)'}"
        )
    return resolved


def _controls_for(pipeline: Any, targets: List[Target]) -> List[Control]:
    return [
        ctrl
        for ctrl in _controls(pipeline)
        if ctrl.filter_to_connect is not None
        and (ctrl.filter_to_connect.name, ctrl.parameter_name_to_connect) in targets
    ]


def apply_overrides(pipeline: Any, overrides: Dict[str, Any], method: str = "snapshot") -> None:
    """Set parameter overrides on the filters and on the controls driving them.

    A value outside a control's range is clamped by the control (like a GUI
    slider): a warning says so.
    """
    resolved = resolve_names(pipeline, list(overrides), method)
    for name, value in overrides.items():
        targets = resolved[name]
        controls = _controls_for(pipeline, targets)
        for ctrl in controls:
            ctrl.value = value  # may raise TypeError / ValueError (wrong type, unknown choice)
            if not _same_value(ctrl.value, value):
                warnings.warn(
                    f"{method}(): {name}={format_value(value)} is outside the range of control "
                    f"{ctrl.name!r} {ctrl.value_range}, clamped to {format_value(ctrl.value)}",
                    stacklevel=4,
                )
        for filter_name, param_name in targets:
            controlled = [ctrl for ctrl in controls if ctrl.filter_to_connect.name == filter_name]  # type: ignore[union-attr]
            final = controlled[0].value if controlled else value
            PipelineCore.parameters.__set__(pipeline, {filter_name: {param_name: final}})  # type: ignore[attr-defined]


def _same_value(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except (TypeError, ValueError):  # e.g. numpy arrays
        return left is right


# ---------------------------------------------------------------------------
# State handling
# ---------------------------------------------------------------------------


@contextmanager
def preserved_state(pipeline: Any) -> Iterator[None]:
    """Restore parameters, control values, output layout, styles and last
    results on exit (also when the body raises)."""
    parameters = deepcopy(PipelineCore.parameters.__get__(pipeline))  # type: ignore[attr-defined]
    control_values = [(ctrl, ctrl.value) for ctrl in _controls(pipeline)]
    outputs = deepcopy(pipeline.outputs)
    framework_state = pipeline.framework_state.snapshot()
    results = getattr(pipeline, "results", None)
    try:
        yield
    finally:
        PipelineCore.parameters.__set__(pipeline, parameters)  # type: ignore[attr-defined]
        for ctrl, value in control_values:
            ctrl.value = value
        pipeline.outputs = outputs
        pipeline.framework_state.restore(framework_state)
        pipeline.results = results


def prepare_inputs(
    pipeline: Any, input_values: Sequence[Any], inputs: Optional[dict], method: str = "snapshot"
) -> None:
    """Set the inputs given to snapshot/sweep, or check the previous ones can be reused."""
    if inputs is not None:
        if input_values:
            raise TypeError(f"{method}(): pass the inputs either positionally or as inputs={{...}}, not both")
        if not isinstance(inputs, dict):
            raise TypeError(f"{method}(): inputs must be a dict {{input_name: value}}, got {type(inputs).__name__}")
        pipeline.inputs = inputs
        return
    if input_values:
        pipeline.inputs = list(input_values)
        return
    expected = list(pipeline.inputs_routing or [])
    try:
        pipeline.inputs  # noqa: B018 - raises RuntimeError when never set
    except RuntimeError:
        if expected:
            raise TypeError(
                f"{method}() needs the inputs of pipeline {pipeline.name!r}: expected {len(expected)} "
                f"({', '.join(str(name) for name in expected)}), e.g. {method}(path, "
                + ", ".join(str(name) for name in expected)
                + "). They are reused by later calls."
            ) from None
        pipeline.inputs = None


def _export(fig: Any, path: PathLike) -> Union[Path, np.ndarray]:
    if path is None:
        return figure_to_rgb(fig)
    return save_figure(fig, path)


def _caption(pipeline: Any, caption: Union[bool, str, None], exclude: Sequence[str] = ()) -> Optional[str]:
    if caption is True:
        text = format_parameters(PipelineCore.parameters.__get__(pipeline), exclude=exclude)  # type: ignore[attr-defined]
        return text or None
    if isinstance(caption, str):
        return caption
    return None


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


def run_snapshot(
    pipeline: "HeadlessPipeline",
    path: PathLike,
    *input_values: Any,
    inputs: Optional[dict] = None,
    output: OutputSelector = None,
    params: Optional[Dict[str, Any]] = None,
    figsize: Optional[Tuple[float, float]] = None,
    dpi: Optional[float] = None,
    title: Optional[str] = None,
    caption: Union[bool, str, None] = True,
    **overrides: Any,
) -> Tuple[Union[Path, np.ndarray], Any]:
    """`snapshot` returning (written path or image, run results)."""
    all_overrides = {**(params or {}), **overrides}
    resolve_names(pipeline, list(all_overrides), "snapshot")  # fail before running anything
    prepare_inputs(pipeline, input_values, inputs, "snapshot")
    with preserved_state(pipeline):
        apply_overrides(pipeline, all_overrides, "snapshot")
        result = pipeline.run()
        grid = select_cells(result_grid(pipeline, result), output)
        fig = render_grid(grid, figsize=figsize, dpi=dpi, title=title, caption=_caption(pipeline, caption))
    return _export(fig, path), result


def snapshot(
    pipeline: "HeadlessPipeline",
    path: PathLike,
    *input_values: Any,
    inputs: Optional[dict] = None,
    output: OutputSelector = None,
    params: Optional[Dict[str, Any]] = None,
    figsize: Optional[Tuple[float, float]] = None,
    dpi: Optional[float] = None,
    title: Optional[str] = None,
    caption: Union[bool, str, None] = True,
    **overrides: Any,
) -> Union[Path, np.ndarray]:
    """Run the pipeline once and render what the GUI would show to a PNG.

    Example:
        ```python
        pipe.snapshot("out.png", img, gain=2.0)
        rgb = pipe.snapshot(None, img)  # (H, W, 3) uint8 array, no file
        ```

    Args:
        path: PNG file to write (parent folders are created); None returns
            the rendered image as an ``(H, W, 3)`` uint8 array instead.
        *input_values: Pipeline inputs. May be omitted when the pipeline
            takes none, or to reuse the inputs of the previous call / run.
        inputs: Inputs as a ``{input_name: value}`` dict instead.
        output: Render only some outputs: a name, an index (reading order)
            or a list of them. Default: the whole layout.
        params: Parameter overrides as a dict - use it for names that clash
            with the options of this method (``title``, ``dpi``, ...).
        figsize: Figure size in inches. Default: derived from the layout and
            the image aspect ratios.
        dpi: Resolution. Default: showing the largest image near its native
            size (80 to 150 dpi).
        title: Figure title.
        caption: True (default) prints the parameter values used under the
            grid, False hides them, a string replaces them.
        **overrides: Parameter values for this call only: a keyword-argument
            name (``gain=2.0``), a control name or ``"filter.param"``.

    Returns:
        The written path, or the image when ``path`` is None.

    Raises:
        TypeError: unknown parameter name (the message lists the available
            ones), or missing inputs.
        FilterError: a filter raised during the run (state is restored).
    """
    written, _ = run_snapshot(
        pipeline,
        path,
        *input_values,
        inputs=inputs,
        output=output,
        params=params,
        figsize=figsize,
        dpi=dpi,
        title=title,
        caption=caption,
        **overrides,
    )
    return written
