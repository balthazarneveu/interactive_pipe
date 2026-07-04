import functools
from typing import Any, Callable, Optional, Union

from interactive_pipe.core.backend import Backend
from interactive_pipe.core.context import REMOVED_CONTEXT_ALIASES
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class


def pipeline(pipeline_function: Callable, **kwargs) -> HeadlessPipeline:
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def interactive_pipeline(
    gui: Union[str, Backend, None] = "auto",
    safe_input_buffer_deepcopy=True,
    cache=False,
    context: Optional[dict] = None,
    markdown_description: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs_gui,
) -> Callable[[Callable[..., Any]], Union[HeadlessPipeline, Callable[..., Any]]]:
    """@interactive_pipeline

    Function decorator to add some controls @interactive_pipeline
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
