from interactive_pipe.helper import _private
import logging


def get_interactive_pipeline_class(gui="auto"):
    selected_gui = None
    if gui is None or gui == "auto":
        if _private.auto_gui is not None:

            selected_gui = _private.auto_gui  # skip selection, used cached one
            logging.debug(f"auto gui already selected {selected_gui}")
        else:
            try:
                __IPYTHON__  # noqa: F821
                selected_gui = "nb"
            except Exception:
                try:
                    from interactive_pipe.graphical.qt_gui import InteractivePipeQT as ChosenGui
                    selected_gui = "qt"
                except Exception as qt_import_execption:
                    try:
                        import matplotlib.pyplot as plt
                        selected_gui = "mpl"
                    except Exception as mpl_import_exception:
                        raise NameError("Error in auto backend choice:\n" +
                                        f"Could not import Qt: {qt_import_execption}\n" +
                                        f"Could not import Matplotlib {mpl_import_exception}"
                                        )
            _private.auto_gui = selected_gui
    else:
        selected_gui = gui
    if selected_gui == "qt":
        from interactive_pipe.graphical.qt_gui import InteractivePipeQT as ChosenGui
    elif selected_gui == "mpl":
        from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib as ChosenGui
    elif selected_gui == "nb":
        from interactive_pipe.graphical.nb_gui import InteractivePipeJupyter as ChosenGui
    elif selected_gui == "gradio":
        from interactive_pipe.graphical.gradio_gui import InteractivePipeGradio as ChosenGui
    else:
        raise NotImplementedError(f"Gui {gui} not available")
    return ChosenGui
