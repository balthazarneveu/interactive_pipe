import functools
import warnings
from typing import Any, Callable, Optional, Union

from interactive_pipe.core.backend import Backend
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class

# Deprecated aliases for 'context' parameter
_CONTEXT_ALIASES = ("global_params", "global_parameters", "global_state", "global_context", "state")


def pipeline(pipeline_function: Callable, **kwargs) -> HeadlessPipeline:
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def interactive_pipeline(
    gui: Union[str, Backend, None] = "auto",
    safe_input_buffer_deepcopy=True,
    cache=False,
    output_canvas=None,
    context: Optional[dict] = None,
    markdown_description: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs_gui,
) -> Callable[[Callable[..., Any]], Union[HeadlessPipeline, Callable[..., Any]]]:
    """@interactive_pipeline

    Function decorator to add some controls @interactive_pipeline
    """
    # Handle deprecated aliases for context parameter
    for alias in _CONTEXT_ALIASES:
        if alias in kwargs_gui:
            warnings.warn(
                f"'{alias}' parameter is deprecated, use 'context' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if context is None:
                context = kwargs_gui.pop(alias)
            else:
                kwargs_gui.pop(alias)  # Ignore if context already provided

    def wrapper(pipeline_function: Callable[..., Any]) -> Union[HeadlessPipeline, Callable[..., Any]]:
        headless_pipeline = HeadlessPipeline.from_function(
            pipeline_function,
            safe_input_buffer_deepcopy=safe_input_buffer_deepcopy,
            cache=cache,
            context=context,
        )
        if output_canvas is not None:
            headless_pipeline.outputs = output_canvas
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
