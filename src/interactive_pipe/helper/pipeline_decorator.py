from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.graphical.gui import InteractivePipeGUI

import functools
from typing import Callable, Union, Optional
from interactive_pipe.helper.choose_backend import get_interactive_pipeline_class


def pipeline(pipeline_function: Callable, **kwargs) -> HeadlessPipeline:
    return HeadlessPipeline.from_function(pipeline_function, **kwargs)


def interactive_pipeline(
    gui="auto",
    safe_input_buffer_deepcopy=True,
    cache=False,
    output_canvas=None,
    global_params: Optional[dict] = None,
    global_parameters: Optional[dict] = None,  # alias for global_params
    global_state: Optional[dict] = None,  # alias for global_params
    global_context: Optional[dict] = None,  # alias for global_params
    context: Optional[dict] = None,  # alias for global_params
    state: Optional[dict] = None,  # alias for global_params
    **kwargs_gui,
) -> Union[HeadlessPipeline, InteractivePipeGUI]:
    """@interactive_pipeline

    Function decorator to add some controls @interactive_pipeline
    """
    def wrapper(pipeline_function):
        headless_pipeline = HeadlessPipeline.from_function(
            pipeline_function,
            safe_input_buffer_deepcopy=safe_input_buffer_deepcopy,
            cache=cache,
            global_params=global_params,
            global_parameters=global_parameters,  # alias for global_params
            global_state=global_state,  # alias for global_params
            global_context=global_context,  # alias for global_params
            context=context,  # alias for global_params
            state=state,  # alias for global_params
        )
        if output_canvas is not None:
            headless_pipeline.outputs = output_canvas
        if gui is None:
            return headless_pipeline
        else:
            InteractivePipeGui = get_interactive_pipeline_class(gui)
            gui_pipeline = InteractivePipeGui(
                pipeline=headless_pipeline, name=pipeline_function.__name__, **kwargs_gui)

        @ functools.wraps(pipeline_function)
        def inner(*args, **kwargs):
            return gui_pipeline.__call__(*args, **kwargs)
        return inner
    return wrapper
