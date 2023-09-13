def get_interactive_pipeline_class(gui="qt"):
    if gui == "qt":
        from interactive_pipe.graphical.qt_gui import InteractivePipeQT as ChosenGui
    elif gui == "mpl":
        from interactive_pipe.graphical.mpl_gui import InteractivePipeMatplotlib as ChosenGui
    elif gui == "nb":
        from interactive_pipe.graphical.nb_gui import InteractivePipeJupyter as ChosenGui
    else:
        raise NotImplementedError(f"Gui {gui} not available")
    return ChosenGui