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
import itertools
import math
import warnings
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Collection, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np

from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.headless.control import Control, MappedChoiceControl, RangeControl
from interactive_pipe.headless.output_check import output_problem, warn_output_problems
from interactive_pipe.headless.snapshot import (
    Grid,
    OutputSelector,
    compact_panel,
    default_sweep_cell,
    figure_to_rgb,
    flat_cells,
    format_parameters,
    format_value,
    grid_size,
    render_grid,
    render_sweep,
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
        # a control shared by several filters sets all of them (one widget, one value)
        found = targets.setdefault(ctrl.name, [])
        for filt, param_name in ctrl.targets:
            if (filt.name, param_name) not in found:
                found.append((filt.name, param_name))
        if not found:
            del targets[ctrl.name]
    return targets


def outputs_downstream_of(pipeline: Any, filter_names: Collection[str]) -> set:
    """Variable names produced by these filters and by every filter fed by
    them (the data-flow graph; values passed through ``context`` are not seen)."""
    changed: set = set()
    for filt in pipeline.filters:  # source order is a topological order
        if filt.name in filter_names or any(name in changed for name in filt.inputs or []):
            changed.update(name for name in filt.outputs or [] if name is not None)
    return changed


def unknown_names_error(pipeline: Any, unknown: Sequence[str], caller: str, reserved: Sequence[str] = ()) -> TypeError:
    """The one message for parameter names that match nothing, used by
    ``pipeline(img, gain=...)``, ``snapshot``, ``sweep`` and the single-filter entry points."""
    targets = parameter_targets(pipeline)
    available = sorted(key for key in targets if "." not in key)
    message = (
        f"{caller} got unexpected keyword argument(s) "
        + ", ".join(repr(name) for name in unknown)
        + f". Available parameters: {', '.join(available) or 'none'}"
    )
    if reserved:
        message += f" (reserved keywords: {', '.join(reserved)})"
    message += "."
    suggestions = [
        f"{name!r} -> {match[0]!r}"
        for name in unknown
        for match in [difflib.get_close_matches(name, list(targets), n=1)]
        if match
    ]
    if suggestions:
        message += " Did you mean " + ", ".join(suggestions) + "?"
    dotted = sorted(key for key in targets if "." in key)
    if dotted:
        message += f" To set the parameter of one filter only, write 'filter.parameter' (e.g. {dotted[0]!r})."
    return TypeError(message)


def resolve_names(
    pipeline: Any, names: Sequence[str], method: str = "snapshot", caller: Optional[str] = None, reserved=()
) -> Dict[str, List[Target]]:
    """Map override names to filter parameters; unknown names raise TypeError
    listing the available ones (with a close match when there is one).

    Accepted spellings: a parameter name (every filter having it), a control
    name (``exposure``, ``gain_1``, ``amplify.gain``) and ``"filter.parameter"``.
    """
    targets = parameter_targets(pipeline)
    unknown = [name for name in names if name not in targets]
    if unknown:
        raise unknown_names_error(pipeline, unknown, caller or f"{method}()", reserved)
    return {name: targets[name] for name in names}


def check_parameters_dict(pipeline: Any, parameters: Any, caller: str) -> None:
    """Validate ``parameters={"filter": {"param": value}}`` before anything is changed.

    Raises:
        TypeError: ``parameters`` is not a dict.
        ValueError: unknown filter / parameter names, or a filter's entry not
            a dict (every problem in one message, with suggestions).
    """
    if not isinstance(parameters, dict):
        raise TypeError(f"{caller}: parameters must be a dict {{filter_name: {{parameter: value}}}}")
    filters = {filt.name: filt for filt in pipeline.filters}
    problems = []
    for filter_name, values in parameters.items():
        if filter_name not in filters:
            close = difflib.get_close_matches(str(filter_name), list(filters), n=1)
            problems.append(f"no filter {filter_name!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
            continue
        if not isinstance(values, dict):
            problems.append(f"parameters[{filter_name!r}] must be a dict {{parameter: value}}")
            continue
        known = list(filters[filter_name].values)
        for param in values:
            if param not in known:
                close = difflib.get_close_matches(str(param), known, n=1)
                problems.append(
                    f"filter {filter_name!r} has no parameter {param!r}"
                    + (f" (did you mean {close[0]!r}?)" if close else "")
                    + f" - its parameters: {', '.join(known) or 'none'}"
                )
    if problems:
        raise ValueError(
            f"{caller} got invalid parameters={{...}}: " + "; ".join(problems) + f". Filters: {', '.join(filters)}."
        )


def _controls_for(pipeline: Any, targets: List[Target]) -> List[Control]:
    return [
        ctrl
        for ctrl in _controls(pipeline)
        if any((filt.name, param_name) in targets for filt, param_name in ctrl.targets)
    ]


def apply_overrides(pipeline: Any, overrides: Dict[str, Any], method: str = "snapshot") -> None:
    """Set parameter overrides on the filters and on the controls driving them.

    A value outside a control's range is clamped by the control (like a GUI
    slider): a warning says so.
    """
    resolved = resolve_names(pipeline, list(overrides), method)
    for name, value in overrides.items():
        value = plain_value(value)
        targets = resolved[name]
        controls = _controls_for(pipeline, targets)
        for ctrl in controls:
            if value is None:  # Control.value = None would silently reset to the default
                raise TypeError(f"{method}(): {name}=None is not a valid value for control {ctrl.name!r}")
            # may raise TypeError / ValueError (wrong type, unknown choice); clamping is warned below, once
            ctrl._set_value_caller_reports_clamp(value)
            expected = ctrl.to_label(value) if isinstance(ctrl, MappedChoiceControl) else value
            if not _same_value(ctrl.value, expected):
                warnings.warn(
                    f"{method}(): {name}={format_value(value)} is outside the range of control "
                    f"{ctrl.name!r} {ctrl.value_range}, clamped to {format_value(ctrl.value)}",
                    stacklevel=4,
                )
        for filter_name, param_name in targets:
            controlled = [
                ctrl for ctrl in controls if (filter_name, param_name) in [(f.name, p) for f, p in ctrl.targets]
            ]
            final = controlled[0].value if controlled else value
            PipelineCore.parameters.__set__(pipeline, {filter_name: {param_name: final}})  # type: ignore[attr-defined]


def plain_value(value: Any) -> Any:
    """numpy scalars -> Python scalars (controls type-check int / float / bool / str)."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        # a RangeControl stores (lo, hi) tuples, a list [lo, hi] is the same value
        return len(left) == len(right) and all(_same_value(a, b) for a, b in zip(left, right))
    try:
        return bool(left == right)
    except (TypeError, ValueError):  # e.g. numpy arrays
        return left is right


# ---------------------------------------------------------------------------
# State handling
# ---------------------------------------------------------------------------


@contextmanager
def preserved_state(pipeline: Any) -> Iterator[None]:
    """Restore parameters, control values, output layout, styles, last
    results, context and events on exit (also when the body raises)."""
    # per-filter dict copies are enough: overrides replace values, never mutate them
    parameters = PipelineCore.parameters.__get__(pipeline)  # type: ignore[attr-defined]
    control_values = [(ctrl, ctrl.value) for ctrl in _controls(pipeline)]
    outputs = deepcopy(pipeline.outputs)
    framework_state = pipeline.framework_state.snapshot()
    results = getattr(pipeline, "results", None)
    run_state = pipeline.save_run_state()
    try:
        yield
    finally:
        pipeline.restore_run_state(run_state)
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


def _output_styles(pipeline: Any) -> dict:
    framework_state = getattr(pipeline, "framework_state", None)
    return dict(framework_state.output_styles) if framework_state is not None else {}


def _export(fig: Any, path: PathLike) -> Union[Path, np.ndarray]:
    if path is None:
        return figure_to_rgb(fig)
    return save_figure(fig, path)


def _caption(pipeline: Any, caption: Union[bool, str, None], exclude: Sequence[Target] = ()) -> Optional[str]:
    """Caption listing the parameter values; ``exclude``: (filter, parameter) pairs left out
    (the swept ones, shown in the cell labels). Another filter's parameter with the
    same name stays."""
    if caption is True:
        parameters = PipelineCore.parameters.__get__(pipeline)  # type: ignore[attr-defined]
        excluded = set(exclude)
        for ctrl in _controls(pipeline):
            # a control shared by several filters is one value: shown once, at its first target
            excluded.update((filt.name, param_name) for filt, param_name in ctrl.targets[1:])
        kept = {
            filter_name: {key: val for key, val in values.items() if (filter_name, key) not in excluded}
            for filter_name, values in parameters.items()
        }
        text = format_parameters(kept)
        return text or None
    if isinstance(caption, str):
        return caption
    return None


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


def fresh_run(pipeline: Any, runs: int = 1, method: str = "snapshot") -> Any:
    """Run like the first run: context back to what was given from outside, events off,
    no cache (``PipelineCore.restart_run_state``), then ``runs`` runs; the last one's results."""
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        raise ValueError(f"{method}(): runs must be a positive int (warm-up runs + 1), got {runs!r}")
    pipeline.restart_run_state()
    for _ in range(runs - 1):
        pipeline.run()
    return pipeline.run()


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
    runs: int = 1,
    **overrides: Any,
) -> Tuple[Union[Path, np.ndarray], Any]:
    """`snapshot` returning (written path or image, run results)."""
    all_overrides = {**(params or {}), **overrides}
    resolve_names(pipeline, list(all_overrides), "snapshot")  # fail before running anything
    prepare_inputs(pipeline, input_values, inputs, "snapshot")
    with preserved_state(pipeline):
        apply_overrides(pipeline, all_overrides, "snapshot")
        result = fresh_run(pipeline, runs, "snapshot")
        grid = select_cells(result_grid(pipeline, result), output)
        warn_output_problems(((cell.name, cell.raw) for cell in flat_cells(grid)), "snapshot", _output_styles(pipeline))
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
    runs: int = 1,
    **overrides: Any,
) -> Union[Path, np.ndarray]:
    """Run the pipeline once and render what the GUI would show to a PNG.

    Each call starts like a first run: the ``context`` holds only what was given
    from outside (``context=`` at construction or in a call), not what filters
    wrote in earlier runs; key-bound events are off and nothing is served from
    the cache. The pipeline's own context, events and cache are put back
    afterwards. A pipeline that needs warm-up runs (an accumulator, a
    simulation) takes ``runs=N``: N runs from that fresh start, the last one shown.

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
        runs: Number of runs from the fresh start (default 1); the last one is shown.
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
        runs=runs,
        **overrides,
    )
    return written


# ---------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------


def _is_range_parameter(pipeline: Any, targets: List[Target]) -> bool:
    if any(isinstance(ctrl, RangeControl) for ctrl in _controls_for(pipeline, targets)):
        return True
    parameters = PipelineCore.parameters.__get__(pipeline)  # type: ignore[attr-defined]
    return any(isinstance(parameters[filt].get(param), tuple) for filt, param in targets)


def _is_sweep_axis(pipeline: Any, targets: List[Target], value: Any) -> bool:
    """list / numpy array -> swept; tuple -> swept unless the parameter is a
    range (RangeControl or a tuple-valued parameter), where a tuple is one value."""
    if isinstance(value, (list, np.ndarray)):
        return True
    if isinstance(value, tuple):
        return not _is_range_parameter(pipeline, targets)
    return False


def values_over_range(pipeline: Any, name: str, targets: List[Target], count: int) -> List[Any]:
    """`count` values spread over the declared range of the control behind `name`."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"steps[{name!r}] must be a positive int, got {count!r}")
    controls = _controls_for(pipeline, targets)
    if not controls:
        raise ValueError(f"steps: {name!r} has no control (no declared range): pass a list of values instead")
    ctrl = controls[0]
    if isinstance(ctrl, RangeControl):
        raise ValueError(f"steps: {name!r} is a RangeControl, pass a list of (lo, hi) pairs instead")
    if ctrl._type is bool:
        return [False, True]
    if ctrl.value_range is None:
        raise ValueError(f"steps: control {ctrl.name!r} has no declared range, pass a list of values instead")
    if ctrl._type is str:
        choices = list(ctrl.value_range)
        if count >= len(choices):
            return choices
        indexes = np.linspace(0, len(choices) - 1, count).round().astype(int)
        return [choices[idx] for idx in dict.fromkeys(indexes.tolist())]
    low, high = ctrl.value_range[0], ctrl.value_range[1]
    if count == 1:
        return [ctrl.value_default]
    if getattr(ctrl, "is_log", False):  # log slider: geometric steps, 3 significant digits
        values = np.array([float(f"{val:.3g}") for val in np.geomspace(float(low), float(high), count)])  # type: ignore[arg-type]
    else:
        values = np.linspace(float(low), float(high), count)  # type: ignore[arg-type]
    if ctrl._type is int:
        return list(dict.fromkeys(int(round(val)) for val in values))
    return [float(val) for val in values]


def split_sweep_arguments(
    pipeline: Any, overrides: Dict[str, Any], steps: Optional[Dict[str, int]]
) -> Tuple[Dict[str, List[Any]], Dict[str, Any]]:
    """Separate swept axes (name -> list of values) from fixed overrides."""
    resolved = resolve_names(pipeline, list(overrides) + list(steps or {}), "sweep")
    axes: Dict[str, List[Any]] = {}
    fixed: Dict[str, Any] = {}
    for name, value in overrides.items():
        if _is_sweep_axis(pipeline, resolved[name], value):
            values = value.tolist() if isinstance(value, np.ndarray) else [plain_value(item) for item in value]
            if not values:
                raise ValueError(f"sweep(): {name} has no values to sweep")
            axes[name] = values
        else:
            fixed[name] = value
    for name, count in (steps or {}).items():
        if name in overrides:
            raise ValueError(f"sweep(): {name!r} is given both as a keyword and in steps=")
        axes[name] = values_over_range(pipeline, name, resolved[name], count)
    if not axes:
        raise ValueError(
            "sweep() needs a parameter to sweep: a list of values (gain=[0.5, 1.0, 2.0]) "
            "or steps over the declared range (steps={'gain': 5})"
        )
    if len(axes) > 2:
        raise ValueError(
            f"sweep() sweeps one or two parameters at a time, got {len(axes)} ({', '.join(axes)}): "
            "fix the others to a single value, or call sweep() once per pair"
        )
    return axes, fixed


def _panel(grid: Grid, output: Any) -> Grid:
    return compact_panel(grid if output == ALL_OUTPUTS else select_cells(grid, output))


def sweep(
    pipeline: "HeadlessPipeline",
    path: PathLike,
    *input_values: Any,
    inputs: Optional[dict] = None,
    output: Any = None,
    steps: Optional[Dict[str, int]] = None,
    params: Optional[Dict[str, Any]] = None,
    figsize: Optional[Tuple[float, float]] = None,
    dpi: Optional[float] = None,
    title: Optional[str] = None,
    caption: Union[bool, str, None] = True,
    runs: int = 1,
    **overrides: Any,
) -> Union[Path, np.ndarray]:
    """Run the pipeline for several parameter values and render a contact sheet.

    Every cell starts like a first run (see ``snapshot``): cells are
    independent of each other and of the runs before the call.

    Example:
        ```python
        pipe.sweep("sweep.png", img, gain=[0.5, 1, 2])  # one row
        pipe.sweep("grid.png", img, gain=[0.5, 2], blur=[1, 3, 5])  # 2 x 3 grid
        pipe.sweep("steps.png", img, steps={"gain": 5})  # 5 values over the slider range
        pipe.sweep("all.png", img, gain=[0.5, 2], output="all")  # every output per cell
        ```

    A list, tuple or numpy array is a swept axis; a scalar is a fixed override
    applied to every cell. For a range parameter (``RangeControl``) a tuple is
    one ``(lo, hi)`` value: sweep it with a list of pairs.

    Args:
        path: PNG to write, or None to get the image as an (H, W, 3) uint8 array.
        *input_values: Pipeline inputs (optional when reusing the previous ones).
        inputs: Inputs as a dict instead.
        output: Output shown in each cell: a name or an index. Default: the
            only output, else the first image output that the swept
            parameters change (downstream of their filters), else the last
            image output. ``"all"`` shows the
            whole layout in every cell; a list shows several outputs.
        steps: ``{name: count}`` sweeps a control over its declared range
            (``count`` evenly spaced values, geometric for a log slider; every
            choice of a dropdown, both states of a checkbox).
        params: Overrides / axes as a dict (for names clashing with options).
        figsize: As for ``snapshot``.
        dpi: As for ``snapshot``.
        title: As for ``snapshot``.
        caption: True prints the fixed parameter values under the sheet.
        runs: Runs per cell from the fresh start (default 1); the last one is shown.
        **overrides: Swept axes (lists) and fixed overrides (scalars).

    Returns:
        The written path, or the image when ``path`` is None.

    Raises:
        ValueError: nothing to sweep, or more than two swept parameters.
        TypeError: unknown parameter name, or missing inputs.
        FilterError: a filter raised (state is restored).
    """
    all_overrides = {**(params or {}), **overrides}
    axes, fixed = split_sweep_arguments(pipeline, all_overrides, steps)
    prepare_inputs(pipeline, input_values, inputs, "sweep")
    names = list(axes)
    combos = list(itertools.product(*(axes[name] for name in names)))
    swept_targets = sorted({target for name in names for target in parameter_targets(pipeline)[name]})
    panels_flat: List[Grid] = []
    run_styles: dict = {}
    with preserved_state(pipeline):
        apply_overrides(pipeline, fixed, "sweep")
        caption_text = _caption(pipeline, caption, exclude=swept_targets)
        chosen_name: Any = None
        for combo in combos:
            apply_overrides(pipeline, dict(zip(names, combo)), "sweep")
            grid = result_grid(pipeline, fresh_run(pipeline, runs, "sweep"))
            run_styles.update(_output_styles(pipeline))  # layout.style calls of this run
            if output is not None:
                panels_flat.append(_panel(grid, output))
                continue
            # default: chosen on the first cell, then kept by name for the others
            # (unless a layout.grid call removed it from this cell's layout)
            cells = flat_cells(grid)
            if chosen_name is None or chosen_name not in [cell.name for cell in cells]:
                changed = outputs_downstream_of(pipeline, {filter_name for filter_name, _ in swept_targets})
                chosen_name = cells[default_sweep_cell(grid, changed)].name
            chosen_cell = next(cell for cell in cells if cell.name == chosen_name)
            panels_flat.append([[chosen_cell]])
    styles = run_styles
    shown = {}  # output name -> first value with a display problem (one warning per output)
    for panel in panels_flat:
        for cell in flat_cells(panel):
            if cell.name not in shown and output_problem(cell.raw, styles.get(cell.name)) is not None:
                shown[cell.name] = cell.raw
    warn_output_problems(shown.items(), "sweep", styles)
    labels = [", ".join(f"{name}={format_value(val)}" for name, val in zip(names, combo)) for combo in combos]
    if len(names) == 1:
        count = len(panels_flat)
        widths, heights = grid_size(panels_flat[0])
        if sum(widths) > 1.5 * sum(heights):
            n_cols = 1  # wide panels (several outputs each): one row per value
        else:
            n_cols = count if count <= 6 else math.ceil(math.sqrt(count))
        panels = [panels_flat[start : start + n_cols] for start in range(0, count, n_cols)]
        cell_labels = [labels[start : start + n_cols] for start in range(0, count, n_cols)]
        fig = render_sweep(panels, cell_labels=cell_labels, figsize=figsize, dpi=dpi, title=title, caption=caption_text)
    else:
        first, second = names
        n_cols = len(axes[second])
        panels = [panels_flat[start : start + n_cols] for start in range(0, len(panels_flat), n_cols)]
        fig = render_sweep(
            panels,
            row_labels=[f"{first}={format_value(val)}" for val in axes[first]],
            column_labels=[f"{second}={format_value(val)}" for val in axes[second]],
            figsize=figsize,
            dpi=dpi,
            title=title,
            caption=caption_text,
        )
    return _export(fig, path)


# ---------------------------------------------------------------------------
# INTERACTIVE_PIPE_SNAPSHOT: GUI call -> snapshot
# ---------------------------------------------------------------------------


def snapshot_instead_of_gui(
    pipeline: "HeadlessPipeline",
    path: Path,
    /,
    *input_values: Any,
    parameters: Optional[dict] = None,
    context: Optional[dict] = None,
    **kwargs: Any,
) -> Any:
    """What a GUI-decorated pipeline call does when ``INTERACTIVE_PIPE_SNAPSHOT``
    is set: same arguments as the GUI call, renders `path` and returns the
    results (a list, like the GUI backends) instead of opening a window.

    Like the GUI call, keyword arguments that match no parameter are ignored
    (with a warning) so unmodified scripts keep running.
    """
    pipeline.update_user_context(context)
    if parameters:
        pipeline.parameters = parameters
    known = parameter_targets(pipeline)
    unknown = [name for name in kwargs if name not in known]
    if unknown:
        warnings.warn(f"INTERACTIVE_PIPE_SNAPSHOT: ignoring unknown keyword argument(s) {unknown}", stacklevel=3)
    overrides = {name: value for name, value in kwargs.items() if name in known}
    # through params=: a parameter named title / output / dpi... is a parameter here
    written, result = run_snapshot(pipeline, path, *input_values, params=overrides)
    print(f"interactive_pipe: snapshot of {pipeline.name!r} written to {written}")
    if result is None:
        return []
    return list(result) if isinstance(result, tuple) else result
