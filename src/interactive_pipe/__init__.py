__version__ = "0.8.0"
from interactive_pipe.helper.pipeline_decorator import pipeline, interactive_pipeline
from interactive_pipe.headless.control import Control, CircularControl
from interactive_pipe.data_objects.curves import Curve, SingleCurve
from interactive_pipe.data_objects.image import Image
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.helper.filter_decorator import interactive, interact

# Allowing more straightforward naming convention
block = interactive
pipeline = interactive_pipeline

# You can usef the following naming convention:
# import interactive_pipe as ip
# @ip.block(...)
# @ip.pipeline(...)
