__version__ = "0.10.1"
# Backend enum for type-safe backend specification
from interactive_pipe.core.backend import Backend

# Clean context API - no more global_params pollution!
from interactive_pipe.core.context import (
    audio,
    context,  # Direct dict-like access
    events,  # Key-bound context events (read-only)
    get_context,
    layout,
)

# Clean exception handling
from interactive_pipe.core.engine import FilterError
from interactive_pipe.core.graph import PipelineSyntaxError
from interactive_pipe.graphical.display import DisplayError

# Data objects
from interactive_pipe.data_objects.curves import Curve, SingleCurve
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.table import Table
from interactive_pipe.data_objects.video import FrameSource, Video
from interactive_pipe.data_objects.webcam import Webcam

# Special controls
from interactive_pipe.headless.control import (
    CircularControl,
    Control,
    RangeControl,
    TextPrompt,
    TimeControl,
)
from interactive_pipe.headless.keyboard import KeyboardControl

# Video inputs: the timeline a Video input brings, its position read as context["timeline"]
from interactive_pipe.headless.timeline import Timeline, TimelineControl

# Mouse input: a clicked point / a dragged region, as fractions of the image size
from interactive_pipe.headless.pointer import PointControl, RegionControl, to_pixels

# Panels
from interactive_pipe.headless.panel import Panel
from interactive_pipe.helper.filter_decorator import interact, interactive
from interactive_pipe.helper.pipeline_decorator import interactive_pipeline

# Animation export (TimeControl pipelines -> GIF / PNG frames)
from interactive_pipe.headless.animation import export_animation

# Drawing on images (points, boxes, lines, polygons, text, masks): interactive_pipe.draw
from interactive_pipe import draw

# Audio helpers (load, STFT, spectrogram, denoise, pitch shift): interactive_pipe.sound
from interactive_pipe import sound

# Agent skill shipped with the package (`interactive-pipe skill`)
from interactive_pipe.agent import skill_path

# Allowing more straightforward naming convention
block = interactive
pipeline = interactive_pipeline

# You can use the following naming convention:
# import interactive_pipe as ip
# @ip.block(...)
# @ip.pipeline(...)

__all__ = [
    "__version__",
    "Backend",
    "FilterError",
    "PipelineSyntaxError",
    "DisplayError",
    "context",
    "layout",
    "audio",
    "events",
    "get_context",
    "Curve",
    "SingleCurve",
    "Image",
    "Table",
    "Video",
    "Webcam",
    "FrameSource",
    "Timeline",
    "TimelineControl",
    "Control",
    "CircularControl",
    "RangeControl",
    "TextPrompt",
    "TimeControl",
    "KeyboardControl",
    "PointControl",
    "RegionControl",
    "to_pixels",
    "Panel",
    "interact",
    "interactive",
    "interactive_pipeline",
    "block",
    "pipeline",
    "export_animation",
    "draw",
    "sound",

    "skill_path",
]
