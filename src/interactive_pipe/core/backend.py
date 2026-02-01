from enum import Enum


class Backend(str, Enum):
    """Supported GUI backends for interactive pipelines."""

    QT = "qt"
    GRADIO = "gradio"
    MPL = "mpl"
    NB = "nb"
    AUTO = "auto"
    HEADLESS = "headless"
