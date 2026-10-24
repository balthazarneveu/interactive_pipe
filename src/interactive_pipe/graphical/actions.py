"""Registry of the GUI actions shared by keyboard shortcuts, menus and help.

Each backend binds the default keys, builds its menu bar (Qt, Dear PyGui)
and prints the F1 help from this single table, so a shortcut, a menu entry
and its help line can never drift apart.
"""

from dataclasses import dataclass
from typing import Tuple

MENU_GROUPS: Tuple[str, ...] = ("File", "View", "Pipeline", "Help")


@dataclass(frozen=True)
class Action:
    """A GUI action: one method of InteractivePipeGUI, one key, one menu entry."""

    name: str
    label: str  # menu entry text and help line
    key: str  # default keyboard shortcut (as passed to on_press)
    menu: str  # one of MENU_GROUPS
    method: str  # name of the InteractivePipeGUI method to call
    doc: str  # longer description (tooltips)

    def __post_init__(self):
        if self.menu not in MENU_GROUPS:
            raise ValueError(f"menu must be one of {MENU_GROUPS}, got {self.menu!r}")


DEFAULT_ACTIONS: Tuple[Action, ...] = (
    Action("save_images", "Save images", "w", "File", "save_images", "save the output images to disk"),
    Action("export_tuning", "Export tuning", "e", "File", "save_parameters", "export parameters to a yaml/json file"),
    Action("import_tuning", "Import tuning", "o", "File", "load_parameters", "import parameters from a yaml/json file"),
    Action("quit", "Quit", "q", "File", "close", "close the GUI"),
    Action("full_screen", "Toggle full screen", "f11", "View", "toggle_full_screen", "toggle full screen"),
    Action("reset", "Reset parameters", "r", "Pipeline", "reset_parameters", "reset sliders to default parameters"),
    Action("print", "Print parameters", "i", "Pipeline", "print_parameters", "print parameters in the console"),
    Action("graph", "Show graph", "g", "Pipeline", "display_graph", "display the execution graph"),
    Action("profile", "Profile last run", "t", "Pipeline", "print_timings", "print per-filter timings of the last run"),
    Action("help", "Keyboard shortcuts", "f1", "Help", "show_help", "show this help"),
)
