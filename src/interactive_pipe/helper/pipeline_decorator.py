import functools
from typing import Any, Callable, Optional, Union

from interactive_pipe.core.backend import Backend
from interactive_pipe.core.context import REMOVED_CONTEXT_ALIASES
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class


def pipeline(pipeline_function: Callable, **kwargs) -> HeadlessPipeline:
    """Build a ``HeadlessPipeline`` from a pipeline function, without any GUI.

    Non-decorator equivalent of ``interactive_pipeline(gui=None)``, handy for
    tests and batch processing. Extra keyword arguments are forwarded to
    ``HeadlessPipeline.from_function``.

    Note: the top-level ``interactive_pipe.pipeline`` alias points to
    ``interactive_pipeline`` (the decorator), not to this helper.
    """
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def interactive_pipeline(
    gui: Union[str, Backend, None] = "auto",
    safe_input_buffer_deepcopy: bool = True,
    cache: Union[bool, str] = False,
    context: Optional[dict] = None,
    markdown_description: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs_gui: Any,
) -> Callable[[Callable[..., Any]], Union[HeadlessPipeline, Callable[..., Any]]]:
    """Decorator turning a pipeline function into an interactive GUI application.

    The decorated function chains filters (typically declared with
    ``@interactive``) and is analyzed statically to build the execution
    graph. Its body must therefore contain only filter-function calls,
    assignments and a return statement — no control flow (if/for/while)
    or arithmetic; put such logic inside the filters themselves.

    Args:
        gui: Backend used to display the pipeline. One of ``"auto"``,
            ``"qt"``, ``"mpl"``, ``"nb"`` (Jupyter widgets), ``"gradio"``
            or a ``Backend`` enum value. ``None`` or ``"headless"``
            returns a ``HeadlessPipeline`` without launching any GUI.
        safe_input_buffer_deepcopy: Deep-copy the input buffers before each
            run so filters cannot mutate the original inputs.
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
            e.g. ``size``.

    Returns:
        A decorator. Applied to a pipeline function it returns either a
        ``HeadlessPipeline`` (when ``gui`` is None or ``"headless"``) or a
        callable that launches the GUI when invoked with the pipeline inputs.

    Raises:
        TypeError: If a removed pre-0.9.0 context alias (``global_params``,
            ``state``, ...) is passed; use ``context={...}`` instead.

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
        headless_pipeline = HeadlessPipeline.from_function(
            pipeline_function,
            safe_input_buffer_deepcopy=safe_input_buffer_deepcopy,
            cache=cache,
            context=context,
        )
        if gui is None or gui == "headless":
            return headless_pipeline
        else:
            InteractivePipeGui = get_interactive_pipeline_class(gui)
            gui_pipeline = InteractivePipeGui(
                pipeline=headless_pipeline,
                markdown_description=markdown_description,
                name=name if name is not None else pipeline_function.__name__,
                **kwargs_gui,
            )

        @functools.wraps(pipeline_function)
        def inner(*args: Any, **kwargs: Any) -> Any:
            return gui_pipeline.__call__(*args, **kwargs)

        # Attach the GUI pipeline object to the function so users can access methods like graph_representation
        setattr(inner, "pipeline", gui_pipeline)
        setattr(inner, "graph_representation", gui_pipeline.graph_representation)

        return inner

    return wrapper
