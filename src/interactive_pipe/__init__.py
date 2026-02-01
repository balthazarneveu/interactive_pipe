__version__ = "0.8.9"
# Backend enum for type-safe backend specification
from interactive_pipe.core.backend import Backend

# Clean context API - no more global_params pollution!
from interactive_pipe.core.context import (
    SharedContext,  # For legacy code migration with explicit injection - deprecated
    audio,
    context,  # Direct dict-like access
    get_context,
    layout,
)

# Clean exception handling
from interactive_pipe.core.engine import FilterError

# Data objects
from interactive_pipe.data_objects.curves import Curve, SingleCurve
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.table import Table

# Special controls
from interactive_pipe.headless.control import (
    CircularControl,
    Control,
    TextPrompt,
    TimeControl,
)
from interactive_pipe.headless.keyboard import KeyboardControl

# Panels
from interactive_pipe.headless.panel import Panel
from interactive_pipe.helper.filter_decorator import interact, interactive
from interactive_pipe.helper.pipeline_decorator import interactive_pipeline

# Allowing more straightforward naming convention
block = interactive
pipeline = interactive_pipeline

# You can usef the following naming convention:
# import interactive_pipe as ip
# @ip.block(...)
# @ip.pipeline(...)
