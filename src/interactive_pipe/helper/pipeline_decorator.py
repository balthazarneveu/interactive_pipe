import functools
import logging
import os
from typing import Any, Callable, Optional, Union

from interactive_pipe.cli import (
    get_snapshot_hook,
    resolve_gui,
    size_from_env,
    snapshot_path_from_env,
    snapshot_requested,
)
from interactive_pipe.core.backend import Backend
from interactive_pipe.core.context import REMOVED_CONTEXT_ALIASES
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class

#: HeadlessPipeline methods also reachable from a GUI-decorated pipeline function
SEE_THE_RESULT_METHODS = ("snapshot", "sweep", "describe", "summary")
#: names people try for "the outputs without a window": they point to `.headless`
WRONG_GUESSES = ("run", "outputs", "results", "compute")


def _pointer_to_headless(function_name: str, guess: str) -> Callable:
    def wrong_guess(*args: Any, **kwargs: Any) -> Any:
        raise AttributeError(
            f"{function_name}.{guess}(...) does not exist: {function_name}(...) opens the window, and "
            f"{function_name}.headless(img, gain=2.0) runs the pipeline without a window and returns its "
            "outputs (a tuple, like a gui=None pipeline)."
        )

    return wrong_guess


def attach_headless(inner: Callable, function_name: str, headless_pipeline: HeadlessPipeline) -> None:
    """``inner.headless``: a HeadlessPipeline of the same function, so
    ``demo.headless(img, gain=2.0)`` returns the outputs (a tuple, like a
    ``gui=None`` pipeline) without opening a window. It is its own pipeline
    (own control values; the GUI reshapes its pipeline's outputs into rows).
    The usual wrong guesses (``demo.run(img)``...) raise, pointing to it."""
    setattr(inner, "headless", headless_pipeline)
    for guess in WRONG_GUESSES:
        setattr(inner, guess, _pointer_to_headless(function_name, guess))


def pipeline(pipeline_function: Callable, **kwargs) -> HeadlessPipeline:
    """Build a ``HeadlessPipeline`` from a pipeline function, without any GUI.

    Non-decorator equivalent of ``interactive_pipeline(gui=None)``, handy for
    tests and batch processing. Extra keyword arguments are forwarded to
    ``HeadlessPipeline.from_function``.

    Note: the top-level ``interactive_pipe.pipeline`` alias points to
    ``interactive_pipeline`` (the decorator), not to this helper.
    """
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def _snapshot_launcher(
    pipeline_function: Callable[..., Any],
    headless_pipeline: HeadlessPipeline,
    gui_pipeline: Any = None,
    headless_twin: Optional[HeadlessPipeline] = None,
) -> Callable:
    """Stand-in for the GUI launcher when INTERACTIVE_PIPE_SNAPSHOT is set.

    `.pipeline` stays the (never shown) GUI object when it could be built, so
    scripts configuring it (``demo.pipeline.bind_key_to_context(...)``) still run.
    """
    from interactive_pipe.headless.explore import snapshot_instead_of_gui

    @functools.wraps(pipeline_function)
    def inner(*args: Any, **kwargs: Any) -> Any:
        hook = get_snapshot_hook()  # set by `interactive-pipe snapshot` / `describe`
        if hook is not None:
            return hook(
                pipeline_function.__name__,
                headless_pipeline,
                lambda path: snapshot_instead_of_gui(headless_pipeline, path, *args, **kwargs),
            )
        path = snapshot_path_from_env(pipeline_function.__name__)
        if path is None:  # unset after decoration
            raise RuntimeError("INTERACTIVE_PIPE_SNAPSHOT was unset after the pipeline was decorated")
        return snapshot_instead_of_gui(headless_pipeline, path, *args, **kwargs)

    owner = gui_pipeline if gui_pipeline is not None else headless_pipeline
    setattr(inner, "pipeline", owner)
    if headless_twin is None:
        headless_twin = HeadlessPipeline.from_function(pipeline_function)
    attach_headless(inner, pipeline_function.__name__, headless_twin)
    setattr(inner, "graph_representation", owner.graph_representation)
    for method_name in SEE_THE_RESULT_METHODS:
        setattr(inner, method_name, getattr(headless_pipeline, method_name))
    return inner


def _gui_for_snapshot(
    selected_gui: Any,
    headless_pipeline: HeadlessPipeline,
    markdown_description: Optional[str],
    name: Optional[str],
    pipeline_function: Callable[..., Any],
    gui_options: dict,
) -> Any:
    """GUI object that is configured but never run (INTERACTIVE_PIPE_SNAPSHOT).

    When the backend cannot be built here (not installed, no display...), a
    windowless stand-in with the same configuration API; None if even that fails."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # the window is never shown
    try:
        gui_class = get_interactive_pipeline_class(selected_gui)
        return gui_class(
            pipeline=headless_pipeline,
            markdown_description=markdown_description,
            name=name if name is not None else pipeline_function.__name__,
            **gui_options,
        )
    except Exception as exc:
        # Broad on purpose: the snapshot only needs the headless pipeline
        reason = str(exc)
    try:
        # Same API as a backend (bind_key_to_context...), so the script still runs
        windowless = _windowless_gui_class()(
            pipeline=headless_pipeline, name=name if name is not None else pipeline_function.__name__
        )
    except Exception as exc:  # noqa: BLE001 - last resort: the headless pipeline
        logging.warning(
            f"INTERACTIVE_PIPE_SNAPSHOT: GUI object not built ({reason}; {exc}), using the headless pipeline"
        )
        return None
    logging.warning(
        f"INTERACTIVE_PIPE_SNAPSHOT: {selected_gui!r} GUI not built ({reason}), using a windowless stand-in"
    )
    return windowless


def _windowless_gui_class() -> type:
    """``InteractivePipeGUI`` of no backend: scripts can configure it, it never runs.

    Stands in for the GUI object under INTERACTIVE_PIPE_SNAPSHOT when the
    requested backend cannot be built (not installed, no display), so a script
    calling ``demo.pipeline.bind_key_to_context(...)`` behaves the same with or
    without the backend."""
    from interactive_pipe.graphical.gui import InteractivePipeGUI

    class WindowlessGUI(InteractivePipeGUI):
        def init_app(self, **kwargs: Any) -> None:
            pass

        def run(self) -> list:
            raise RuntimeError("this GUI object has no window: it only stands in under INTERACTIVE_PIPE_SNAPSHOT")

    return WindowlessGUI


def interactive_pipeline(
    gui: Union[str, Backend, None] = "auto",
    safe_input_buffer_deepcopy: Optional[bool] = None,
    cache: Union[bool, str] = False,
    readonly_inputs: bool = True,
    context: Optional[dict] = None,
    markdown_description: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs_gui: Any,
) -> Callable[[Callable[..., Any]], Union[HeadlessPipeline, Callable[..., Any]]]:
    """Decorator turning a pipeline function into an interactive GUI application.

    The decorated function chains filters (typically declared with
    ``@interactive``) and is analyzed statically to build the execution
    graph. Its body must therefore contain only filter-function calls
    (possibly nested, with literal keyword arguments such as
    ``amplify(img, gain=2.0)``), assignments and one final return — no
    control flow (if/for/while) or arithmetic; put such logic inside the
    filters themselves. Anything else raises ``PipelineSyntaxError`` at
    decoration time, naming the line and the fix.

    Args:
        gui: Backend used to display the pipeline. One of ``"auto"``,
            ``"qt"``, ``"mpl"``, ``"nb"`` (Jupyter widgets), ``"gradio"``
            or a ``Backend`` enum value. ``None`` or ``"headless"``
            returns a ``HeadlessPipeline`` without launching any GUI.
        safe_input_buffer_deepcopy: Deep-copy the input buffers before each
            run. None (default) copies only inputs that the read-only
            machinery cannot protect (anything but numpy arrays / torch
            tensors when ``readonly_inputs`` is True); True always copies
            (one full copy of the inputs per run); False never copies.
        readonly_inputs: Hand filters their numpy inputs as read-only views
            (default True), so in-place mutation (``img += 1``) raises
            immediately instead of silently corrupting sibling filters or
            cached buffers. Declare ``@interactive(inplace=True)`` on a filter
            that intentionally mutates its inputs (it then receives private
            writable copies), or pass False to restore the permissive
            behavior.
        cache: Cache intermediate filter outputs between runs.
            - False (default): recompute every filter on every interaction.
            - True: sequential prefix cache - a change recomputes every
              filter after it in source order.
            - "graph": dependency-aware cache - only filters actually
              affected by a change are recomputed, following the data-flow
              graph and runtime-tracked ``context`` usage.
            - "graph-strict": same as "graph", but context reads return
              numpy arrays as read-only views so accidental in-place
              mutation raises at the offending line (debug helper).
        context: Initial content of the shared context dictionary, readable
            and writable from filters through the ``context`` proxy.
        markdown_description: Description displayed by backends that support
            it (e.g. Gradio).
        name: Window/application title. Defaults to the function name.
        **kwargs_gui: Extra options forwarded to the GUI backend,
            e.g. ``size`` (``(w, h)``, ``"fullscreen"`` or ``"maximized"``),
            or ``restore_session=True`` to remember the slider values
            between launches (saved on exit to
            ``~/.interactive_pipe/sessions/<name>.yaml`` unless
            ``session_path`` is given).

    Environment overrides (read when the decorator is applied):
        ``INTERACTIVE_PIPE_GUI`` (auto/qt/dpg/mpl/nb/gradio/headless/none)
        replaces ``gui`` when it is ``"auto"`` (the default), and
        ``INTERACTIVE_PIPE_SIZE`` ("fullscreen", "maximized" or "WxH")
        provides ``size`` when none is given. Explicit arguments win over
        the environment; ``interactive_pipe.cli.parse_gui_args`` values are
        explicit arguments, so the command line wins over both.

        ``INTERACTIVE_PIPE_SNAPSHOT`` (a PNG path or folder, ``{name}`` is
        replaced by the function name): when set, any GUI ``gui`` value
        returns a launcher that renders a snapshot there and returns the
        results instead of opening a window (``gui=None`` is unaffected).

    Returns:
        A decorator. Applied to a pipeline function it returns either a
        ``HeadlessPipeline`` (when ``gui`` is None or ``"headless"``) or a
        callable that launches the GUI when invoked with the pipeline inputs.
        Both have ``.headless``, the ``HeadlessPipeline`` itself:
        ``my_pipeline.headless(img, gain=2.0)`` returns the outputs without
        opening a window (whatever ``gui``), ``.snapshot`` / ``.sweep`` /
        ``.describe`` / ``.summary`` render or describe it.

    Raises:
        TypeError: If a removed pre-0.9.0 context alias (``global_params``,
            ``state``, ...) is passed; use ``context={...}`` instead.
        PipelineSyntaxError: If the pipeline body contains a statement the
            static analysis cannot express (see the guide).

    Example:
        ```python
        @interactive_pipeline(gui="qt", cache=True)
        def my_pipeline(img):
            flipped = flip(img)
            amplified = amplify(flipped)
            return flipped, amplified

        my_pipeline(input_image)  # opens the interactive window
        ```
    """
    # Reject removed aliases of the 'context' parameter with a clear message
    for alias in REMOVED_CONTEXT_ALIASES:
        if alias in kwargs_gui:
            raise TypeError(
                f"@interactive_pipeline: '{alias}' argument was removed in interactive_pipe 0.9.0; "
                "pass context={...} instead."
            )

    def wrapper(pipeline_function: Callable[..., Any]) -> Union[HeadlessPipeline, Callable[..., Any]]:
        def build() -> HeadlessPipeline:
            return HeadlessPipeline.from_function(
                pipeline_function,
                safe_input_buffer_deepcopy=safe_input_buffer_deepcopy,
                cache=cache,
                readonly_inputs=readonly_inputs,
                context=context,
            )

        headless_pipeline = build()
        # Environment overrides (INTERACTIVE_PIPE_GUI / INTERACTIVE_PIPE_SIZE), see interactive_pipe.cli
        selected_gui = resolve_gui(gui)
        if selected_gui is None or selected_gui == "headless":
            return headless_pipeline
        if snapshot_requested():
            # INTERACTIVE_PIPE_SNAPSHOT: render a PNG instead of opening a window
            return _snapshot_launcher(
                pipeline_function,
                headless_pipeline,
                _gui_for_snapshot(
                    selected_gui, headless_pipeline, markdown_description, name, pipeline_function, dict(kwargs_gui)
                ),
                build(),
            )
        else:
            gui_options = dict(kwargs_gui)
            if gui_options.get("size") is None:
                env_size = size_from_env()
                if env_size is not None:
                    gui_options["size"] = env_size
            InteractivePipeGui = get_interactive_pipeline_class(selected_gui)
            gui_pipeline = InteractivePipeGui(
                pipeline=headless_pipeline,
                markdown_description=markdown_description,
                name=name if name is not None else pipeline_function.__name__,
                **gui_options,
            )

        @functools.wraps(pipeline_function)
        def inner(*args: Any, **kwargs: Any) -> Any:
            return gui_pipeline.__call__(*args, **kwargs)

        # Attach the GUI pipeline object to the function so users can access methods like graph_representation
        setattr(inner, "pipeline", gui_pipeline)
        # the same pipeline without a window: demo.headless(img, gain=2.0) returns the outputs
        attach_headless(inner, pipeline_function.__name__, build())
        setattr(inner, "graph_representation", gui_pipeline.graph_representation)
        # See-the-result loop without opening the window (same calls as on a HeadlessPipeline)
        for method_name in SEE_THE_RESULT_METHODS:
            setattr(inner, method_name, getattr(headless_pipeline, method_name))

        return inner

    return wrapper
