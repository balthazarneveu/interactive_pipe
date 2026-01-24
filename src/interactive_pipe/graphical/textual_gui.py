from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.textual_window import TextualWindow
from interactive_pipe.headless.keyboard import KeyboardControl
from typing import Optional, Union, Tuple
import logging
import sys
import os
import contextlib
from io import StringIO

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Static, Header, Footer, Switch, Select, Input
    from textual.containers import Container, Horizontal, Vertical, Grid
    from textual.binding import Binding
    from textual.message import Message

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    logging.warning("Textual is not available. Install with: pip install textual")


class InteractivePipeTextualApp(App):
    """Textual App wrapper for the interactive pipeline window"""

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("r", "reset", "Reset"),
        Binding("q", "quit", "Quit"),
        Binding("w", "save_images", "Save Images"),
        Binding("o", "load_params", "Load Parameters"),
        Binding("e", "save_params", "Save Parameters"),
        Binding("i", "print_params", "Print Parameters"),
        Binding("g", "display_graph", "Display Graph"),
    ]

    CSS = """
    #main {
        layout: vertical;
    }
    #images {
        height: 60%;
    }
    #controls {
        height: 40%;
        border-top: solid $primary;
    }
    """

    def on_unhandled_exception(self, event):
        """Handle unhandled exceptions to prevent app from crashing"""
        logging.error(
            f"Unhandled exception in Textual app: {event.exception}", exc_info=True
        )
        # Don't exit the app - let it continue running
        event.stop()

    def __init__(self, main_gui, window, **kwargs):
        super().__init__(**kwargs)
        self.main_gui = main_gui
        self.window = window
        self.title = main_gui.name if main_gui.name else "Interactive Pipeline"

    def compose(self) -> ComposeResult:
        """Compose the UI layout"""
        yield Header(show_clock=False)

        # Main content area
        with Container(id="main"):
            # Image display area - use Grid for image layout
            yield Grid(id="images")

            # Controls area
            yield Vertical(id="controls")

        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted"""
        try:
            # Set up the window's app reference
            self.window.app = self
            self.window.screen = self.screen

            # Initialize controls
            self.window.init_sliders(self.main_gui.controls)

            # Set up image grid
            images_grid = self.query_one("#images", Grid)
            controls_container = self.query_one("#controls", Vertical)

            # Store reference to image grid in window
            self.window.image_grid = images_grid

            # Add control widgets to controls container
            for widget_name, widget in self.window.control_widgets.items():
                # Create a horizontal container for label + widget
                label = Static(f"{widget_name}:")
                label.styles.width = 20
                controls_container.mount(label)
                controls_container.mount(widget)

            # Initial refresh - wrap in try/except to prevent app crash
            try:
                self.window.refresh()
            except Exception as e:
                logging.error(f"Error during initial refresh: {e}", exc_info=True)
                # Show error message but don't exit
                error_msg = Static(f"Error: {str(e)}", id="error_message")
                controls_container.mount(error_msg)
        except Exception as e:
            logging.error(f"Error in on_mount: {e}", exc_info=True)
            # Don't re-raise - let the app continue running

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle Input widget value changes"""
        widget = event.input
        if hasattr(widget, "_update_func"):
            widget._update_func(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle Switch widget value changes"""
        widget = event.switch
        if hasattr(widget, "_update_func"):
            widget._update_func(event.value)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle Select widget value changes"""
        widget = event.select
        if hasattr(widget, "_update_func"):
            # Select.Changed has the value in event.value
            widget._update_func(event.value)

    def action_help(self):
        """Show help"""
        self.main_gui.help()

    def action_reset(self):
        """Reset parameters"""
        self.main_gui.reset_parameters()
        self.window.reset_sliders()

    def action_quit(self):
        """Quit the app"""
        self.main_gui.close()

    def action_save_images(self):
        """Save images"""
        self.main_gui.save_images()

    def action_load_params(self):
        """Load parameters"""
        self.main_gui.load_parameters()
        self.window.reset_sliders()

    def action_save_params(self):
        """Save parameters"""
        self.main_gui.save_parameters()

    def action_print_params(self):
        """Print parameters"""
        self.main_gui.print_parameters()

    def action_display_graph(self):
        """Display graph"""
        self.main_gui.display_graph()


class InteractivePipeTextual(InteractivePipeGUI):
    """Interactive pipeline with Textual TUI backend"""

    def init_app(self, **kwargs):
        if not TEXTUAL_AVAILABLE:
            raise ImportError(
                "Textual is not available. Install with: pip install textual"
            )

        self.window = TextualWindow(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            **kwargs,
        )
        self.set_default_key_bindings()

    def set_default_key_bindings(self):
        """Set up default key bindings"""
        self.key_bindings = {
            **{
                "f1": self.help,
                "r": self.reset_parameters,
                "w": self.save_images,
                "o": self.load_parameters,
                "e": self.save_parameters,
                "i": self.print_parameters,
                "q": self.close,
                "g": self.display_graph,
            },
            **self.key_bindings,
        }

    def run(self) -> list:
        """Run the Textual app"""
        # Check if inputs are initialized, but don't fail if they're not
        # The app should still run and allow user interaction
        if not self.pipeline._PipelineCore__initialized_inputs:
            # Initialize with empty inputs if not already done
            # This allows the app to start even if inputs aren't set
            try:
                self.pipeline.inputs = []
            except Exception:
                pass

        # Redirect logging and stderr to avoid polluting the terminal
        # Create a log file for errors/warnings
        log_file_path = os.path.join(
            os.path.expanduser("~"), ".interactive_pipe_textual.log"
        )

        # Set up logging to file
        file_handler = logging.FileHandler(log_file_path, mode="a")
        file_handler.setLevel(logging.WARNING)  # Only warnings and errors
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # Get root logger and add file handler
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        root_logger.addHandler(file_handler)

        # Suppress console output for warnings/debug messages during app run
        # Keep stderr available for Textual's own error handling
        original_level = root_logger.level
        suppressed_handlers = []

        try:
            # Suppress console handlers (but keep file handler)
            # Only suppress StreamHandlers that write to stderr/stdout
            for handler in root_logger.handlers:
                if isinstance(handler, logging.StreamHandler):
                    if handler.stream in (sys.stderr, sys.stdout):
                        # Temporarily raise level to ERROR to suppress warnings/debug
                        original_handler_level = handler.level
                        handler.setLevel(logging.ERROR)
                        suppressed_handlers.append((handler, original_handler_level))

            # Also suppress interactive_pipe logger specifically
            ip_logger = logging.getLogger("interactive_pipe")
            ip_original_level = ip_logger.level
            ip_logger.setLevel(logging.ERROR)

            # Create and run the Textual app
            app = InteractivePipeTextualApp(
                main_gui=self,
                window=self.window,
            )
            # Store app reference for close method
            self.window.app = app
            # Run the app - this blocks until the app exits
            # Textual's app.run() will handle the event loop
            app.run()

        finally:
            # Restore original logging configuration
            root_logger.level = original_level
            ip_logger.setLevel(ip_original_level)

            # Restore handler levels
            for handler, original_level in suppressed_handlers:
                handler.setLevel(original_level)

            # Remove file handler
            if file_handler in root_logger.handlers:
                root_logger.removeHandler(file_handler)
            file_handler.close()

            # Restore original handlers
            root_logger.handlers = original_handlers

        self.custom_end()
        return self.pipeline.results

    def close(self):
        """Close the GUI"""
        super().close()
        if hasattr(self, "window") and self.window.app:
            self.window.app.exit()

    def reset_parameters(self):
        """Reset parameters to default values"""
        super().reset_parameters()
        if hasattr(self, "window"):
            self.window.reset_sliders()

    def load_parameters(self):
        """Load parameters from file"""
        super().load_parameters()
        if hasattr(self, "window"):
            # Update control widgets with loaded values
            for widget_name, widget in self.window.control_widgets.items():
                if widget_name in self.window.ctrl:
                    ctrl = self.window.ctrl[widget_name]
                    if hasattr(widget, "value"):
                        widget.value = ctrl.value
                    elif hasattr(widget, "set_value"):
                        widget.set_value(ctrl.value)
            self.window.reset_sliders()

    def on_press(self, key_pressed, refresh_func=None):
        """Handle key press events"""
        if refresh_func is None:
            refresh_func = self.window.refresh if hasattr(self, "window") else None
        super().on_press(key_pressed, refresh_func=refresh_func)

    def refresh(self):
        """Refresh the display"""
        if hasattr(self, "window"):
            self.window.refresh()
