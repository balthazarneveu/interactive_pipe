"""Single-filter entry points attached to every ``@interactive`` function.

GitHub issue #21: a lone filter should be easy to run, look at and test.
``@interactive`` keeps returning a plain function (picklable, ``functools.wraps``
metadata, direct calls keep working); these helpers are attached to it as
attributes:

```python
@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0): ...

amplify.snapshot("amp.png", img, gain=2.0)
amplify.sweep("amp_sweep.png", img, gain=[0.5, 1, 2])
amplify.describe()  # amplify.describe(img) also names the outputs
amplify.interact(img)  # open the GUI on this filter alone
```

Each call builds a throwaway one-filter pipeline around the decorated
function. The registered ``Control`` objects (shared through
``Control._registry`` with the real pipelines using the filter) are borrowed:
their filter connection and value are restored afterwards, so the filter keeps
working in its pipelines.
"""

from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from interactive_pipe.core.context import _set_user_context
from interactive_pipe.core.engine import FilterError
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.signature import analyze_apply_fn_signature
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.pipeline import HeadlessPipeline

#: attributes added to each @interactive function
FILTER_ENTRY_POINTS = ("snapshot", "sweep", "describe", "summary", "interact")


def _ordered_inputs(func: Callable, method: str, input_values: Sequence[Any], inputs: Optional[dict]) -> List[Any]:
    """Positional inputs of the filter, checked against its signature."""
    names = analyze_apply_fn_signature(func)[0]
    if inputs is not None:
        if input_values:
            raise TypeError(f"{func.__name__}.{method}(): pass the inputs positionally or as inputs={{...}}, not both")
        missing = [name for name in names if name not in inputs]
        if missing:
            raise TypeError(f"{func.__name__}.{method}(): inputs={{...}} misses {missing}")
        input_values = [inputs[name] for name in names]
    if len(input_values) != len(names):
        expected = ", ".join(names) if names else "no input"
        raise TypeError(
            f"{func.__name__}.{method}() expects {len(names)} input(s) ({expected}), got {len(input_values)}"
        )
    return list(input_values)


def _deduce_outputs(filt: FilterCore, input_values: List[Any]) -> List[str]:
    """Output names from a dry run, like ``@interact`` does: one name per
    returned element (a tuple / list return is several outputs)."""
    try:
        out = filt.run(*input_values)
    except FilterError:
        raise
    except Exception as exc:
        # Broad on purpose: arbitrary user filter code, reported like a pipeline run
        raise FilterError(filt.name, exc, exc.__traceback__) from exc
    if out is None:
        return []
    count = len(out)
    if count == 1:
        return [filt.name]
    return [f"{filt.name}[{idx}]" for idx in range(count)]


@contextmanager
def single_filter_pipeline(
    func: Callable, input_values: Optional[List[Any]], method: str = "snapshot"
) -> Iterator[HeadlessPipeline]:
    """One-filter HeadlessPipeline around a decorated function.

    `input_values` None builds it without inputs nor dry run (outputs unknown).
    The registered controls are connected to the throwaway filter for the
    duration of the block, then given back their previous connection and value.
    """
    input_names = analyze_apply_fn_signature(func)[0]
    controls: Dict[str, Control] = dict(Control.get_controls(func))
    saved: List[Tuple[Control, Any, Any, Any, Any]] = [
        (ctrl, ctrl.filter_to_connect, ctrl.parameter_name_to_connect, ctrl.update_param_func, ctrl.value)
        for ctrl in controls.values()
    ]
    try:
        filt = FilterCore(
            apply_fn=func,
            name=func.__name__,
            inputs=list(input_names),
            outputs=None,
            inplace=bool(getattr(func, "__interactive_pipe_inplace__", False)),
        )
        filt.values = {param_name: ctrl.value for param_name, ctrl in controls.items()}
        pipeline = HeadlessPipeline(filters=[filt], name=func.__name__, inputs=list(input_names), outputs=[])
        outputs: Optional[List[Union[int, str]]] = None
        if input_values is not None:
            # dry run with the pipeline's context set, so filters using `context` work
            _set_user_context(pipeline._user_context)
            try:
                outputs = list(_deduce_outputs(filt, input_values))
            finally:
                _set_user_context(None)
        filt.outputs = outputs
        pipeline.outputs = outputs
        for param_name, ctrl in controls.items():
            ctrl.connect_filter(filt, param_name)
        pipeline.controls = list(controls.values())
        if input_values is not None:
            pipeline.inputs = list(input_values)
        yield pipeline
    finally:
        for ctrl, filter_to_connect, parameter_name, update_param_func, value in saved:
            ctrl.filter_to_connect = filter_to_connect
            ctrl.parameter_name_to_connect = parameter_name
            ctrl.update_param_func = update_param_func
            ctrl.value = value


def attach_filter_entry_points(func: Callable) -> None:
    """Attach snapshot / sweep / describe / summary / interact to a decorated filter."""

    def snapshot(path: Any, *input_values: Any, inputs: Optional[dict] = None, **options: Any) -> Any:
        """Run this filter alone and render its outputs to a PNG.

        Same options as ``HeadlessPipeline.snapshot`` (``output``, ``params``,
        ``figsize``, ``dpi``, ``title``, ``caption`` and parameter overrides);
        the filter inputs are required (except for a filter taking none).
        Returns the written path, or an (H, W, 3) uint8 array when path is None.
        """
        values = _ordered_inputs(func, "snapshot", input_values, inputs)
        with single_filter_pipeline(func, values, "snapshot") as pipeline:
            return pipeline.snapshot(path, **options)

    def sweep(path: Any, *input_values: Any, inputs: Optional[dict] = None, **options: Any) -> Any:
        """Run this filter alone for several parameter values and render a
        contact sheet (same options as ``HeadlessPipeline.sweep``:
        ``gain=[0.5, 1, 2]``, ``steps={"gain": 5}``, ``output``...)."""
        values = _ordered_inputs(func, "sweep", input_values, inputs)
        with single_filter_pipeline(func, values, "sweep") as pipeline:
            return pipeline.sweep(path, **options)

    def describe(*input_values: Any, inputs: Optional[dict] = None) -> dict:
        """Describe this filter's inputs, controls and parameters as a dict.

        Outputs are named only when inputs are given (a dry run counts them).
        """
        values = None
        if input_values or inputs is not None or not analyze_apply_fn_signature(func)[0]:
            values = _ordered_inputs(func, "describe", input_values, inputs)
        with single_filter_pipeline(func, values, "describe") as pipeline:
            return pipeline.describe()

    def summary(*input_values: Any, inputs: Optional[dict] = None) -> str:
        """Text version of describe()."""
        values = None
        if input_values or inputs is not None or not analyze_apply_fn_signature(func)[0]:
            values = _ordered_inputs(func, "summary", input_values, inputs)
        with single_filter_pipeline(func, values, "summary") as pipeline:
            return pipeline.summary()

    def interact(*input_values: Any, gui: Union[str, Any] = "auto", **gui_kwargs: Any) -> Any:
        """Open the GUI on this filter alone (``@interact`` after the fact).

        Blocks until the window is closed and returns the last results. The
        control values are given back afterwards, so pipelines using this
        filter are not affected by the slider moves.
        """
        from interactive_pipe.cli import get_snapshot_hook, snapshot_path_from_env
        from interactive_pipe.headless.explore import snapshot_instead_of_gui
        from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class

        values = _ordered_inputs(func, "interact", input_values, None)
        with single_filter_pipeline(func, values, "interact") as pipeline:
            hook = get_snapshot_hook()  # `interactive-pipe snapshot`: names the file, counts the call
            if hook is not None:
                return hook(func.__name__, pipeline, lambda path: snapshot_instead_of_gui(pipeline, path, *values))
            snapshot_path = snapshot_path_from_env(func.__name__)
            if snapshot_path is not None:  # INTERACTIVE_PIPE_SNAPSHOT: no window
                return snapshot_instead_of_gui(pipeline, snapshot_path, *values)
            gui_class = get_interactive_pipeline_class(gui)
            gui_kwargs.setdefault("name", func.__name__)
            gui_pipeline = gui_class(pipeline=pipeline, **gui_kwargs)
            try:
                return gui_pipeline(*values)
            finally:
                gui_pipeline.close()

    for entry_point in (snapshot, sweep, describe, summary, interact):
        entry_point.__qualname__ = f"{func.__qualname__}.{entry_point.__name__}"
        setattr(func, entry_point.__name__, entry_point)
