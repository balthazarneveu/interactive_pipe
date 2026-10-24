import logging
import time
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional

from interactive_pipe.data_objects.data import Data
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.graphical.actions import DEFAULT_ACTIONS, MENU_GROUPS, Action
from interactive_pipe.headless.control import TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.headless.pipeline import HeadlessPipeline


class InteractivePipeGUI:
    """Adds a generic graphical user interface to HeadlessPipeline.

    Needs to be specified/customized for each backend.
    It adds an app with a GUI on top of a HeadlessPipeline.
    Widgets will update the pipeline parameters.
    - It deals with key bindings
     (keyboard press triggers a function.
     function docstring is shown to the user when he presses "F1" help)
    - It deals with printing the help
    - Initializing the app `init_app` usually requires creating the window object
    A few special methods may be redefined for some specific backend needs.
    `reset_parameters`, `close`,
    `save_parameters`, `load_parameters`, `print_parameters`
    `display_graph`, `show_help`
    The default actions (keys, menu entries, help lines) come from the
    registry in `interactive_pipe.graphical.actions`.
    - `ask_path` asks the user for a file path (terminal by default,
      native file dialogs on Qt and Dear PyGui).
    - Redefining `print_message` will allow a window popup for instance.

    Do not re-implement the init function!
    """

    def __init__(
        self,
        pipeline: Optional[HeadlessPipeline] = None,
        controls: Optional[List] = None,
        name: str = "",
        custom_end: Callable = lambda: None,
        audio: bool = False,
        size=None,
        **kwargs,
    ) -> None:
        if controls is None:
            controls = []
        if pipeline is None:
            raise ValueError("pipeline must be provided")
        self.pipeline = pipeline
        self.custom_end = custom_end
        self.audio = audio
        self.name = name
        self.size = size
        merged_controls = []
        merged_controls += controls
        if hasattr(pipeline, "controls"):
            merged_controls += pipeline.controls
        self.controls = merged_controls
        if self.pipeline.outputs:
            if not isinstance(self.pipeline.outputs[0], list):
                self.pipeline.outputs = [self.pipeline.outputs]
        # Framework state (output styles, events, audio, pipeline backref)
        # lives on pipeline.framework_state - the pipeline sets it up at
        # construction; the GUI only resets the display styles here.
        self.pipeline.framework_state.output_styles.clear()
        self.key_bindings = {}
        self.context_key_bindings = {}
        self.init_app(**kwargs)
        self.reset_context_events()

    def init_app(self):
        """Init the app
        Initializing the app requires
        - creating the window object
        - binding default keyboard keys
        """
        raise NotImplementedError

    def run(self) -> list:
        """Once properly initialized
        - Show the window
        - Put it in full screen if needed
        - execute the app (launch the main event loop)
        Return results
        """
        raise NotImplementedError

    def __call__(self, *args, parameters=None, context=None, **kwargs) -> list:
        if parameters is None:
            parameters = {}
        # Handle context parameter - update user context if provided
        self.pipeline.update_user_context(context)
        self.pipeline.parameters = parameters
        self.pipeline.parameters = self.pipeline.parameters_from_keyword_args(**kwargs)
        self.pipeline.inputs = list(args)
        results = self.run()
        return results

    @staticmethod
    def _binding_identity(func: Callable) -> tuple:
        # partial(update, name, flag) objects are rebuilt whenever widgets are
        # re-initialized; compare the wrapped function and its arguments instead
        return (getattr(func, "func", func), getattr(func, "args", ()), tuple(getattr(func, "keywords", {}).items()))

    def bind_key(self, key, func: Callable):
        previous = self.key_bindings.get(key)
        if previous is not None and self._binding_identity(previous) != self._binding_identity(func):
            logging.warning(f"Key {key} already bound to {previous}")
        self.key_bindings[key] = func

    def bind_key_to_context(self, key: str, context_param_name: str, doc: str):
        self.context_key_bindings[key] = {"param_name": context_param_name, "doc": doc}
        # Not triggered!
        self.pipeline.framework_state.events[context_param_name] = False

    def reset_context_events(self):
        for evkey in self.pipeline.framework_state.events.keys():
            self.pipeline.framework_state.events[evkey] = False

    def on_press(self, key_pressed, refresh_func=None):
        for key, func in self.key_bindings.items():
            if key_pressed == key:
                func()  # a GUI level function like reset parameters or export images
        triggered_events = []
        for key, event_dict in self.context_key_bindings.items():
            event_triggered = key_pressed == key
            self.pipeline.framework_state.events[event_dict["param_name"]] = event_triggered
            if event_triggered:
                logging.info(f"TRIGGERED A KEY EVENT {key_pressed} - {event_dict['doc']}")
                triggered_events.append(event_dict["param_name"])
        if triggered_events:
            # only the filters reading these events (and what depends on them) rerun
            self.pipeline.invalidate_event_readers(triggered_events)
            if refresh_func is not None:
                refresh_func()
        self.reset_context_events()

    def bind_keyboard_slider(self, ctrl: KeyboardControl, key_update_parameter_func: Callable):
        if not isinstance(ctrl, KeyboardControl):
            raise TypeError(f"ctrl must be a KeyboardControl instance, got {type(ctrl)}")
        toggle_only = True
        doc = ""
        slider_name = ctrl.name
        toggle_only = ctrl.keyup is None or ctrl.keydown is None

        for keyboard_key, down_flag in [(ctrl.keyup, False), (ctrl.keydown, True)]:
            if keyboard_key is None:
                continue
            if toggle_only:
                if ctrl._type is bool:
                    doc = f"toggle {ctrl.name}"
                else:
                    if ctrl.keyup is None:
                        doc = f"decrease {ctrl.name}"
                    elif ctrl.keydown is None:
                        doc = f"increase {ctrl.name}"
            else:
                if down_flag:
                    formatted_keydown = self._format_key_for_help(ctrl.keydown) if ctrl.keydown else ""
                    formatted_keyup = self._format_key_for_help(ctrl.keyup) if ctrl.keyup else ""
                    doc = f"[{formatted_keydown}]/[{formatted_keyup}]: {ctrl.name}"
                else:
                    doc = None
            update_func = partial(key_update_parameter_func, slider_name, down_flag)
            self.bind_key(keyboard_key, update_func)
            update_func.__doc__ = doc

    def play_pause_time(self, suspend_resume_timer: Optional[Callable] = None):
        """Play or pause the timer"""
        if self.start_time is None:
            self.start_time = time.time()
        else:
            self.start_time = time.time() - self.start_time
        self.time_playing = not self.time_playing
        if suspend_resume_timer is not None:
            suspend_resume_timer(not self.time_playing)

    def plug_timer_control(
        self,
        ctrl: TimeControl,
        update_parameter_func: Callable,
        suspend_resume_timer: Optional[Callable] = None,
    ):
        """Plug timer control to the processing block (pass the time to the block)
        Bind the pause_resume_key (default "p") play/pause key to the timer
        """
        if not isinstance(ctrl, TimeControl):
            raise TypeError(f"ctrl must be a TimeControl instance, got {type(ctrl)}")
        doc = ""
        slider_name = ctrl.name
        doc = None
        self.start_time = time.time()
        self.time_playing = True

        def update_func():
            if self.start_time is None:
                self.start_time = time.time()
            delta_time = time.time() - self.start_time
            return update_parameter_func(slider_name, delta_time)

        pause_resume_func = partial(self.play_pause_time, suspend_resume_timer)
        pause_resume_func.__doc__ = f"pause/resume time control '{slider_name}'"
        self.bind_key(ctrl.pause_resume_key, pause_resume_func)
        update_func.__doc__ = doc
        return update_func

    # ---------------------------------------------------------------------
    # Actions registry

    @classmethod
    def default_actions(cls) -> List[Action]:
        """Registry actions this backend implements (e.g. no fullscreen on mpl)."""
        return [action for action in DEFAULT_ACTIONS if callable(getattr(cls, action.method, None))]

    @classmethod
    def actions_by_menu(cls) -> Dict[str, List[Action]]:
        """Default actions grouped by menu, in menu bar order (empty menus skipped)."""
        grouped: Dict[str, List[Action]] = {group: [] for group in MENU_GROUPS}
        for action in cls.default_actions():
            grouped[action.menu].append(action)
        return {group: actions for group, actions in grouped.items() if actions}

    def run_action(self, action: Action):
        """Run an action's method (menu entries call this, keys go through on_press)."""
        return getattr(self, action.method)()

    def set_default_key_bindings(self):
        """Bind the registry keys; bindings already set by the user win."""
        defaults = {action.key: getattr(self, action.method) for action in self.default_actions()}
        self.key_bindings = {**defaults, **self.key_bindings}

    # ---------------------------------------------------------------------
    # File paths

    def ask_path(self, title: str, save: bool, extensions: List[str], default_name: str) -> Optional[Path]:
        """Ask the user for a file path; None means cancelled.

        The base implementation prompts in the terminal (empty input cancels).
        Backends override it with a native file dialog.
        """
        answer = Data.prompt_file(f"{title} [{default_name}] (empty to cancel): ").strip()
        if not answer:
            return None
        return Path(answer)

    def _with_path(
        self,
        title: str,
        save: bool,
        extensions: List[str],
        default_name: str,
        on_path: Callable[[Path], None],
    ):
        """Ask for a path and run `on_path(path)` unless the user cancelled.

        Callback based so that backends with asynchronous file dialogs
        (Dear PyGui) can run `on_path` later from the dialog callback.
        """
        path = self.ask_path(title, save, extensions, default_name)
        if path is not None:
            on_path(path)

    def _default_file_stem(self) -> str:
        return self.name.replace(" ", "_") if self.name else "pipeline"

    # ---------------------------------------------------------------------

    def reset_parameters(self):
        """reset parameters"""
        logging.debug("Reset parameters")

    def close(self):
        """quit"""
        logging.debug("Closing gui")

    def save_parameters(self):
        """export parameters dictionary to a yaml/json file"""
        extensions = Parameters(None).file_extensions

        def export(path: Path):
            path = Parameters.check_path(path, load=False, extensions=extensions)
            self.pipeline.export_tuning(path, override=True)
            logging.info(f"Exported tuning to {path}")

        default_name = f"{self._default_file_stem()}_tuning{extensions[-1]}"
        self._with_path("Export tuning", True, extensions, default_name, export)

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        extensions = Parameters(None).file_extensions

        def load(path: Path):
            self.pipeline.import_tuning(path)
            self.on_parameters_loaded()

        default_name = f"{self._default_file_stem()}_tuning{extensions[-1]}"
        self._with_path("Import tuning", False, extensions, default_name, load)

    def on_parameters_loaded(self):
        """Sync the widgets after `load_parameters` (backends override this)."""

    def print_parameters(self):
        """print parameters dictionary in the console"""
        print(self.pipeline.__repr__())

    def save_images(self):
        """save images to disk"""
        extensions = Image(None).file_extensions

        def save(path: Path):
            path = Image.check_path(path, load=False, extensions=extensions)
            self.pipeline.save(path, data_wrapper_fn=lambda im: Image(im), save_entire_buffer=True)

        default_name = f"{self._default_file_stem()}{extensions[0]}"
        self._with_path("Save images", True, extensions, default_name, save)

    def graph_representation(self, path=None, ortho=True, view=False):
        """Generate graph representation of the pipeline"""
        return self.pipeline.graph_representation(path=path, ortho=ortho, view=view)

    def display_graph(self):
        """display execution graph"""
        try:
            result = self.pipeline.graph_representation(view=True, ortho=False)
            if result is None:
                self.print_message(
                    [
                        "Graph visualization failed.",
                        "Graphviz executables are required to display the graph.",
                        "Please install Graphviz system package:",
                        "  - Ubuntu/Debian: sudo apt-get install graphviz",
                        "  - macOS: brew install graphviz",
                        "  - Windows: Download from https://graphviz.org/download/",
                    ]
                )
        except Exception as exc:
            # Broad on purpose: graph display is an optional extra triggered by
            # a key binding; surface the failure to the user, never crash.
            self.print_message(
                [
                    f"Failed to display graph: {exc}",
                    "Graphviz executables are required to display the graph.",
                    "Please install Graphviz system package:",
                    "  - Ubuntu/Debian: sudo apt-get install graphviz",
                    "  - macOS: brew install graphviz",
                    "  - Windows: Download from https://graphviz.org/download/",
                ]
            )

    def _format_key_for_help(self, key: str) -> str:
        """Format a key string for display in help text.

        Converts special keys like spacebar to readable names.
        """
        if key == " " or key == KeyboardControl.KEY_SPACEBAR:
            return "SPACEBAR"
        return key

    def _format_docstring_for_help(self, docstring: str) -> str:
        """Format a docstring to replace spacebar references with readable text."""
        # Replace [" "] with [SPACEBAR] in docstrings
        return docstring.replace('[" "]', "[SPACEBAR]")

    def show_help(self) -> List[str]:
        """print this help in the console"""
        help_lines = []
        action_by_key = {action.key: action for action in self.default_actions()}
        for key, func in self.key_bindings.items():
            action = action_by_key.get(key)
            if action is not None and func == getattr(self, action.method):
                help_lines.append(f"[{self._format_key_for_help(key)}]    : {action.label}")
            elif func.__doc__ is not None:
                if func.__doc__.startswith("["):
                    formatted_doc = self._format_docstring_for_help(func.__doc__)
                    help_lines.append(f"{formatted_doc}")
                else:
                    formatted_key = self._format_key_for_help(key)
                    formatted_doc = self._format_docstring_for_help(func.__doc__)
                    help_lines.append(f"[{formatted_key}]    : {formatted_doc}")
        for key_context, event_dict in self.context_key_bindings.items():
            formatted_key_context = self._format_key_for_help(key_context)
            formatted_doc = self._format_docstring_for_help(event_dict["doc"])
            # filters read these flags through the `events` context proxy
            help_lines.append(f"[{formatted_key_context}]    : {formatted_doc} (event '{event_dict['param_name']}')")
        self.print_message(help_lines)
        return help_lines

    # kept for backward compatibility (show_help avoids shadowing the builtin name)
    help = show_help

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))

    # ---------------------------------------------------------------------
