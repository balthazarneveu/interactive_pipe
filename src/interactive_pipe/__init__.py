__version__ = "0.8.8"
from interactive_pipe.helper.pipeline_decorator import pipeline, interactive_pipeline
from interactive_pipe.headless.control import (
    Control,
    CircularControl,
    TextPrompt,
    TimeControl,
)
from interactive_pipe.data_objects.curves import Curve, SingleCurve
from interactive_pipe.data_objects.image import Image
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.helper.filter_decorator import interactive, interact

# Clean context API - no more global_params pollution!
from interactive_pipe.core.context import (
    get_context,
    context,  # Direct dict-like access
    layout,
    audio,
    SharedContext,  # For legacy code migration with explicit injection
)

# Clean exception handling
from interactive_pipe.core.engine import FilterError

# Allowing more straightforward naming convention
block = interactive
pipeline = interactive_pipeline

# You can usef the following naming convention:
# import interactive_pipe as ip
# @ip.block(...)
# @ip.pipeline(...)
