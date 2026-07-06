"""Per-output-type gradio builders and converters.

Extracted from gradio_gui.py (tech-debt item 1). The output-type switch
lives here exactly once, in two symmetric halves:
- build_output_container: dry-run detection -> which gradio component hosts
  each pipeline output (plus the canvas cell "type" tag).
- convert_output_value: per-refresh conversion of a pipeline output into the
  value that component expects.
"""

import logging
from typing import Any, Callable, Optional, Tuple

import gradio as gr
import numpy as np

MPL_SUPPORT = False
try:
    import matplotlib.pyplot as plt

    from interactive_pipe.data_objects.curves import Curve
    from interactive_pipe.data_objects.table import Table

    MPL_SUPPORT = True
except ImportError:
    pass


def build_output_container(out_item, title: str) -> Tuple[gr.components.Component, Optional[str]]:  # type: ignore[reportInvalidTypeForm]
    """Pick the gradio container for a pipeline output (dry-run detection).

    Returns (component, type_tag); type_tag is stored in the canvas cell
    ("audio"/"image"/"curve"/"table") - str outputs carry no tag (pinned).
    """
    if isinstance(out_item, np.ndarray):
        if len(out_item.shape) == 1:
            return gr.Audio(label=title), "audio"
        return gr.Image(format="png", type="numpy", label=title), "image"
    elif MPL_SUPPORT and isinstance(out_item, Curve):
        return gr.Plot(label=title), "curve"
    elif isinstance(out_item, Table):
        return gr.Dataframe(label=title), "table"
    # @TODO: https://github.com/balthazarneveu/interactive_pipe/issues/50 support audio!
    elif isinstance(out_item, str):
        return gr.Textbox(label=title), None
    raise NotImplementedError(f"output type {type(out_item)} not supported")


def convert_output_value(out_item, *, audio_sampling_rate: int, convert_image: Callable) -> Any:
    """Convert one pipeline output into the value its gradio container expects."""
    if MPL_SUPPORT and isinstance(out_item, Curve):
        # https://github.com/balthazarneveu/interactive_pipe/issues/54
        # Update curves instead of creating new ones shall be faster
        # Gradio still flickers anyway.
        fig, ax = plt.subplots()
        Curve._plot_curve(out_item.data, ax=ax)
        return fig
    elif isinstance(out_item, Table):
        # Convert to format expected by gr.Dataframe
        # Format: list of lists with first row as headers
        # Use _format_values() to apply precision formatting
        # Check if this is a headerless table (all columns are empty)
        has_headers = any(col != "" for col in out_item.columns)
        if has_headers:
            return [out_item.columns] + out_item._format_values()
        # Headerless table - just show values
        return out_item._format_values()
    elif isinstance(out_item, np.ndarray):
        if len(out_item.shape) == 1:
            logging.debug("CONVERTING AUDIO")
            return (audio_sampling_rate, out_item)
        logging.debug("CONVERTING IMAGE")
        return convert_image(out_item)
    elif isinstance(out_item, str):
        return out_item
    raise NotImplementedError(f"output type {type(out_item)} not suported")
