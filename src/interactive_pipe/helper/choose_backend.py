import logging
import signal
from typing import Union

from interactive_pipe.core.backend import Backend
from interactive_pipe.helper import _private


def get_interactive_pipeline_class(gui: Union[str, Backend, None] = "auto"):
    selected_gui = None
    if gui is None or gui == "auto":
        if _private.auto_gui is not None:
            selected_gui = _private.auto_gui  # skip selection, used cached one
            logging.debug(f"auto gui already selected {selected_gui}")
        else:
            try:
                __IPYTHON__  # type: ignore  # noqa: F821
                selected_gui = "nb"
            except NameError:
                try:
                    from interactive_pipe.graphical.qt_gui import (
                        InteractivePipeQT as ChosenGui,
                    )

                    selected_gui = "qt"
                except ImportError as qt_import_exception:
                    try:
                        import matplotlib.pyplot as plt  # noqa: F401

                        selected_gui = "mpl"
                    except ImportError as mpl_import_exception:
                        raise NameError(
                            "Error in auto backend choice:\n"
                            + f"Could not import Qt: {qt_import_exception}\n"
                            + f"Could not import Matplotlib {mpl_import_exception}"
                        )
            _private.auto_gui = selected_gui
    else:
        selected_gui = gui
    if selected_gui == "qt":
        # Deliberate: reset handlers to default so Ctrl-C / SIGTERM kill the
        # Qt event loop. Side effect: clobbers any handlers a host application
        # installed. If revisited, save/restore around the Qt event loop or
        # make it opt-out.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        from interactive_pipe.graphical.qt_gui import (  # noqa: F811
            InteractivePipeQT as ChosenGui,
        )
    elif selected_gui == "mpl":
        from interactive_pipe.graphical.mpl_gui import (
            InteractivePipeMatplotlib as ChosenGui,
        )
    elif selected_gui == "nb":
        from interactive_pipe.graphical.nb_gui import (
            InteractivePipeJupyter as ChosenGui,
        )
    elif selected_gui == "gradio":
        from interactive_pipe.graphical.gradio_gui import (
            InteractivePipeGradio as ChosenGui,
        )
    else:
        raise NotImplementedError(f"Gui {gui} not available")
    return ChosenGui
