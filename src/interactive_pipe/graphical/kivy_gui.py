import os
import numpy as np
from typing import List
from pathlib import Path
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.graphical.kivy_control import ControlFactory
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.control import Control, TimeControl
import logging
import time
import subprocess

# Disable Kivy's argument parser to avoid conflicts with argparse
# This must be set BEFORE importing any Kivy modules
os.environ.setdefault("KIVY_NO_ARGS", "1")
# Suppress MTD (multitouch device) warnings - these are harmless permission warnings
os.environ.setdefault("KIVY_LOG_LEVEL", "warning")

KIVY_AVAILABLE = False
try:
    # Configure Kivy before importing to suppress MTD warnings
    # Disable MTD (multitouch device) provider to avoid permission warnings
    os.environ.setdefault("KIVY_METRICS_DENSITY", "1")

    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.image import Image as KivyImage
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.core.window import Window
    from kivy.graphics.texture import Texture
    from kivy.clock import Clock
    from kivy.uix.popup import Popup

    # Suppress MTD warnings by filtering logger
    from kivy.logger import Logger
    import logging as kivy_logging

    # Create filter to suppress MTD-related warnings
    class MTDFilter(kivy_logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return (
                "MTD" not in msg
                and "multitouch" not in msg.lower()
                and "event5" not in msg
            )

    Logger.addFilter(MTDFilter())

    KIVY_AVAILABLE = True
except ImportError:
    logging.warning("Kivy not available")

MPL_SUPPORT = False
try:
    from interactive_pipe.data_objects.curves import Curve, SingleCurve
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from io import BytesIO
    from PIL import Image as PILImage

    MPL_SUPPORT = True
except ImportError:
    pass


class InteractivePipeKivy(InteractivePipeGUI):
    def init_app(self, **kwargs):
        if not KIVY_AVAILABLE:
            raise ModuleNotFoundError("Kivy is not installed")
        self.app = KivyApp(
            controls=self.controls,
            name=self.name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self,
            **kwargs,
        )
        self.pipeline.global_params["__pipeline"] = self.pipeline
        self.set_default_key_bindings()

        if self.audio:
            self.audio_player()

    def run(self) -> list:
        assert (
            self.pipeline._PipelineCore__initialized_inputs
        ), "Did you forget to initialize the pipeline inputs?"
        self.app.run()
        self.custom_end()
        return self.pipeline.results

    def set_default_key_bindings(self):
        self.key_bindings = {
            **{
                "f1": self.help,
                "f11": self.toggle_full_screen,
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

    def close(self):
        """close GUI"""
        # Stop any playing audio before closing
        if self.audio and hasattr(self, "_audio_process"):
            self.__stop()
        if hasattr(self, "app"):
            self.app.stop()

    def reset_parameters(self):
        """reset sliders to default parameters"""
        super().reset_parameters()
        if hasattr(self.app, "root") and hasattr(self.app.root, "window"):
            for widget_idx, ctrl in self.app.root.window.ctrl.items():
                if isinstance(ctrl, TimeControl):
                    self.start_time = None
                ctrl.value = ctrl.value_default
            self.app.root.window.reset_sliders()

    def load_parameters(self):
        """import parameters dictionary from a yaml/json file on disk"""
        super().load_parameters()
        if hasattr(self.app, "root") and hasattr(self.app.root, "window"):
            for widget_idx, widget in self.app.root.window.ctrl.items():
                matched = False
                for filtname, params in self.pipeline.parameters.items():
                    for param_name in params.keys():
                        if param_name == widget.parameter_name_to_connect:
                            logging.info(
                                f"MATCH & update {filtname} {widget_idx} with"
                                + f"{self.pipeline.parameters[filtname][param_name]}"
                            )
                            self.app.root.window.ctrl[widget_idx].update(
                                self.pipeline.parameters[filtname][param_name]
                            )
                            matched = True
                assert (
                    matched
                ), f"could not match widget {widget_idx} with parameter to connect {widget.parameter_name_to_connect}"
            self.app.root.window.reset_sliders()

    def print_message(self, message_list: List[str]):
        print("\n".join(message_list))
        if hasattr(self, "app") and hasattr(self.app, "window"):
            popup = Popup(
                title=self.name,
                content=Label(text="\n".join(message_list), color=(0, 0, 0, 1)),
                size_hint=(0.8, 0.8),
            )
            popup.open()

    def toggle_full_screen(self):
        """toggle full screen"""
        if Window.fullscreen in (False, "0", 0, ""):
            Window.fullscreen = "auto"
        else:
            Window.fullscreen = False

    # ---------------------------- AUDIO FEATURE ----------------------------------------

    def audio_player(self):
        """Initialize audio player using subprocess (bypasses SDL2 threading issues)"""
        self._audio_process = None
        self._audio_file = None
        self.pipeline.global_params["__sound"] = None
        self.pipeline.global_params["__set_audio"] = self.__set_audio
        self.pipeline.global_params["__play"] = self.__play
        self.pipeline.global_params["__pause"] = self.__pause
        self.pipeline.global_params["__stop"] = self.__stop

    def handle_audio_error(self, message):
        """Handle audio playback errors"""
        logging.warning(f"Audio error: {message}")

    def __set_audio(self, file_path):
        """Set audio file to play (uses subprocess to avoid SDL2 threading issues)"""
        self.__stop()

        if file_path is None:
            return
        if isinstance(file_path, str):
            file_path = Path(file_path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        else:
            file_path = file_path.resolve()
        if not file_path.exists():
            self.handle_audio_error(f"Audio file not found: {file_path}")
            return

        self._audio_file = file_path
        logging.debug(f"Audio file set: {file_path}")

    def __play(self):
        """Play the audio file using subprocess"""
        if self._audio_file is None:
            logging.debug("No audio file set to play")
            return

        # Stop any currently playing audio
        if self._audio_process is not None:
            self.__stop()

        file_path = self._audio_file
        file_ext = file_path.suffix.lower()

        # Try different audio players in order of preference
        # ffplay is most universal, then paplay (PulseAudio), then aplay (ALSA)
        players = [
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(file_path)],
            ["paplay", str(file_path)],
            ["aplay", str(file_path)] if file_ext == ".wav" else None,
        ]

        for player_cmd in players:
            if player_cmd is None:
                continue
            try:
                # Check if the player exists
                which_result = subprocess.run(
                    ["which", player_cmd[0]], capture_output=True, timeout=1
                )
                if which_result.returncode != 0:
                    continue

                # Start playing in background
                self._audio_process = subprocess.Popen(
                    player_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                logging.debug(f"Playing audio with {player_cmd[0]}: {file_path}")
                return
            except FileNotFoundError:
                continue
            except Exception as e:
                logging.debug(f"Failed to play with {player_cmd[0]}: {e}")
                continue

        self.handle_audio_error(
            "No audio player found. Please install ffmpeg (ffplay), pulseaudio (paplay), "
            "or alsa-utils (aplay) to enable audio playback."
        )

    def __pause(self):
        """Pause/stop the audio playback"""
        self.__stop()

    def __stop(self):
        """Stop the audio playback"""
        if self._audio_process is not None:
            try:
                self._audio_process.terminate()
                self._audio_process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._audio_process.kill()
            except Exception:
                pass
            self._audio_process = None


class KivyApp(App):
    def __init__(
        self, controls=[], name="", pipeline=None, size=None, main_gui=None, **kwargs
    ):
        super().__init__()
        self.controls = controls
        self._app_name = name  # Store name separately since App.name is read-only
        self.pipeline = pipeline
        self.size = size
        self.main_gui = main_gui

    def build(self):
        self.title = self._app_name
        root = BoxLayout(orientation="horizontal")
        self.window = MainWindow(
            controls=self.controls,
            name=self._app_name,
            pipeline=self.pipeline,
            size=self.size,
            main_gui=self.main_gui,
        )
        root.add_widget(self.window)
        return root

    def on_start(self):
        # Set window background to light gray (matching Qt default)
        Window.clearcolor = (0.95, 0.95, 0.95, 1)  # RGBA: light gray
        # Set window size
        if self.size is not None:
            if isinstance(self.size, str):
                if "full" in self.size.lower():
                    Window.fullscreen = "auto"
                elif "max" in self.size.lower():
                    Window.maximize()
            elif isinstance(self.size, int):
                Window.size = (self.size, self.size)
            elif isinstance(self.size, (tuple, list)):
                Window.size = tuple(self.size)
        # Bind keyboard events
        Window.bind(on_keyboard=self.on_keyboard)
        # Trigger initial refresh to display images
        if hasattr(self, "window"):
            Clock.schedule_once(lambda dt: self.window.refresh(), 0.1)

    def on_stop(self):
        """Called when the app is closing - cleanup audio"""
        if self.main_gui is not None and hasattr(self.main_gui, "_audio_process"):
            if self.main_gui._audio_process is not None:
                try:
                    self.main_gui._audio_process.terminate()
                    self.main_gui._audio_process.wait(timeout=0.5)
                except Exception:
                    try:
                        self.main_gui._audio_process.kill()
                    except Exception:
                        pass

    def on_keyboard(self, window, key, *args):
        # Map Kivy key codes to string representations
        key_mapping = {
            273: KeyboardControl.KEY_UP,  # Up arrow
            274: KeyboardControl.KEY_DOWN,  # Down arrow
            275: KeyboardControl.KEY_RIGHT,  # Right arrow
            276: KeyboardControl.KEY_LEFT,  # Left arrow
            280: KeyboardControl.KEY_PAGEUP,  # Page Up
            281: KeyboardControl.KEY_PAGEDOWN,  # Page Down
            32: KeyboardControl.KEY_SPACEBAR,  # Space
            282: "f1",
            283: "f2",
            284: "f3",
            285: "f4",
            286: "f5",
            287: "f6",
            288: "f7",
            289: "f8",
            290: "f9",
            291: "f10",
            292: "f11",
            293: "f12",
        }
        mapped_key = key_mapping.get(key)
        if mapped_key is None:
            # Try to get character from keycode
            try:
                mapped_key = chr(key).lower()
            except (ValueError, OverflowError):
                return False
        if hasattr(self, "window") and hasattr(self.window, "main_gui"):
            self.window.main_gui.on_press(mapped_key, refresh_func=self.window.refresh)
        return True


class MainWindow(BoxLayout, InteractivePipeWindow):
    def __init__(
        self,
        controls=[],
        name="",
        pipeline: HeadlessPipeline = None,
        size=None,
        main_gui=None,
        **kwargs,
    ):
        BoxLayout.__init__(self, orientation="vertical")
        InteractivePipeWindow.__init__(self, name=name, pipeline=pipeline, size=size)
        self.main_gui = main_gui
        self.pipeline.global_params["__window"] = self
        self._window_size = (
            size  # Use different name to avoid conflict with Kivy's size property
        )

        # Create image grid layout - will be updated dynamically
        # Initialize with 1 column, will be updated when images are added
        self.image_grid_layout = GridLayout(
            cols=1, spacing=10, padding=10, size_hint_y=None, size_hint_x=1.0
        )
        self.image_scroll = ScrollView(size_hint_x=1.0, size_hint_y=0.7)
        self.image_scroll.add_widget(self.image_grid_layout)

        # Create controls panel - vertical layout that sizes to content
        self.controls_panel = BoxLayout(
            orientation="vertical", size_hint_y=None, size_hint_x=1.0
        )
        # Bind controls panel height to its minimum height
        self.controls_panel.bind(minimum_height=self.controls_panel.setter("height"))
        # Use a non-scrolling container - just use BoxLayout directly since we don't want scrolling
        # Wrap in a container to maintain size_hint behavior
        controls_container = BoxLayout(
            orientation="vertical", size_hint_x=1.0, size_hint_y=0.3
        )
        controls_container.add_widget(self.controls_panel)

        # Add both panels to main layout - images on top, controls below
        self.add_widget(self.image_scroll)
        self.add_widget(controls_container)

        self.init_sliders(controls)

    @property
    def window_size(self):
        return self._window_size

    @window_size.setter
    def window_size(self, _size):
        self._window_size = _size

    def init_sliders(self, controls: List[Control]):
        self.ctrl = {}
        self.result_label = {}
        self.name_label = {}
        self.widget_list = {}
        control_factory = ControlFactory()

        for ctrl in controls:
            slider_name = ctrl.name
            self.ctrl[slider_name] = ctrl
            if isinstance(ctrl, KeyboardControl):
                self.main_gui.bind_keyboard_slider(ctrl, self.key_update_parameter)
            elif isinstance(ctrl, TimeControl):
                # Use Clock to create a timer
                def create_timer(ctrl_obj):
                    def timer_callback(dt):
                        if (
                            hasattr(self.main_gui, "start_time")
                            and self.main_gui.start_time is not None
                        ):
                            if (
                                hasattr(self.main_gui, "time_playing")
                                and self.main_gui.time_playing
                            ):
                                delta_time = time.time() - self.main_gui.start_time
                                self.update_parameter(ctrl_obj.name, delta_time)

                    return timer_callback

                timer_func = create_timer(ctrl)
                self.main_gui.suspend_resume_timer = lambda suspend: (
                    Clock.unschedule(timer_func)
                    if suspend
                    else Clock.schedule_interval(
                        timer_func, ctrl.update_interval_ms / 1000.0
                    )
                )
                self.main_gui.plug_timer_control(
                    ctrl, self.update_parameter, self.main_gui.suspend_resume_timer
                )
                Clock.schedule_interval(timer_func, ctrl.update_interval_ms / 1000.0)
            elif isinstance(ctrl, Control):
                slider_instance = control_factory.create_control(
                    ctrl, self.update_parameter
                )
                if slider_instance is None:
                    continue
                if ctrl._type == str and ctrl.icons is not None:
                    ctrl.filter_to_connect.cache = False
                    ctrl.filter_to_connect.cache_mem = None
                try:
                    control_widget = slider_instance.create()
                    if control_widget is None:
                        logging.warning(
                            f"Control widget for {slider_name} is None, skipping"
                        )
                        continue
                    # Ensure widget has proper size hints
                    if (
                        hasattr(control_widget, "size_hint_x")
                        and control_widget.size_hint_x is None
                    ):
                        control_widget.size_hint_x = 1.0
                    if (
                        hasattr(control_widget, "size_hint_y")
                        and control_widget.size_hint_y is None
                    ):
                        # For vertical layout, widgets should have size_hint_y=None with explicit height
                        pass  # Keep as None if it's set that way
                    self.widget_list[slider_name] = slider_instance
                    self.controls_panel.add_widget(control_widget)
                except Exception as e:
                    logging.error(
                        f"Error creating control widget for {slider_name}: {e}"
                    )
                    continue

    def update_parameter(self, idx, value):
        """Required implementation for graphical controllers update"""
        if self.ctrl[idx]._type == str:
            if self.ctrl[idx].value_range is None:
                self.ctrl[idx].update(value)
            else:
                if isinstance(value, int):
                    # Index-based selection for dropdown/icon buttons
                    self.ctrl[idx].update(self.ctrl[idx].value_range[value])
                else:
                    self.ctrl[idx].update(value)
        elif self.ctrl[idx]._type == bool:
            self.ctrl[idx].update(bool(value))
        elif self.ctrl[idx]._type == float:
            if isinstance(self.ctrl[idx], TimeControl):
                self.ctrl[idx].update(value)
            else:
                self.ctrl[idx].update(value)
        elif self.ctrl[idx]._type == int:
            self.ctrl[idx].update(int(value))
        else:
            raise NotImplementedError(f"{self.ctrl[idx]._type} not supported")
        self.refresh()

    def key_update_parameter(self, idx, down):
        """Required implementation for keyboard sliders update"""
        if down:
            self.ctrl[idx].on_key_down()
        else:
            self.ctrl[idx].on_key_up()
        self.refresh()

    def add_image_placeholder(self, row, col):
        # Create container for title and image
        container = BoxLayout(
            orientation="vertical", size_hint_y=None, size_hint_x=1.0, height=400
        )
        title_label = Label(
            text=f"{row} {col}",
            size_hint_y=None,
            height=30,
            size_hint_x=1.0,
            color=(0, 0, 0, 1),
        )
        image_widget = KivyImage(size_hint_y=1.0, size_hint_x=1.0)
        container.add_widget(title_label)
        container.add_widget(image_widget)

        self.image_canvas[row][col] = {
            "image": image_widget,
            "title": title_label,
            "container": container,
            "ax_placeholder": None,
        }
        self.image_grid_layout.add_widget(container)

    def set_image_canvas(self, image_grid):
        # Override to update grid layout columns
        expected_image_canvas_shape = (
            len(image_grid),
            max([len(image_row) for image_row in image_grid]),
        )
        # Update grid layout columns
        self.image_grid_layout.cols = expected_image_canvas_shape[1]
        # Call parent implementation
        super().set_image_canvas(image_grid)

    def delete_image_placeholder(self, img_widget_dict):
        container = img_widget_dict.get("container")
        if container is not None and hasattr(container, "parent"):
            if container.parent:
                container.parent.remove_widget(container)
        for obj_key, img_widget in img_widget_dict.items():
            if obj_key == "ax_placeholder" and img_widget is not None:
                # Matplotlib axes cleanup if needed
                pass
            elif (
                obj_key not in ["container", "image", "title"]
                and img_widget is not None
            ):
                if hasattr(img_widget, "parent") and img_widget.parent:
                    img_widget.parent.remove_widget(img_widget)

    def update_image(self, image_array_original, row, col):
        if (
            isinstance(image_array_original, np.ndarray)
            and len(image_array_original.shape) == 1
        ):
            logging.warning(
                "Audio playback not supported with 1D signal in Kivy backend"
            )
            logging.warning("We'll try to display the audio signal as a curve instead")
            if MPL_SUPPORT:
                image_array_original = Curve(
                    [
                        SingleCurve(
                            y=image_array_original,
                        )
                    ],
                    ylabel="Amplitude",
                )
            else:
                return
        elif (
            isinstance(image_array_original, np.ndarray)
            and len(image_array_original.shape) > 1
        ):
            if len(image_array_original.shape) == 2:
                # Grayscale image
                image_array = image_array_original.copy()
                c = 3
                image_array = np.expand_dims(image_array, axis=-1)
                image_array = np.repeat(image_array, c, axis=-1)
            elif len(image_array_original.shape) == 3:
                assert image_array_original.shape[-1] == 3
                image_array = image_array_original
            else:
                raise NotImplementedError(
                    f"{image_array_original.shape} 4+ dimensions not supported"
                )
            # Convert to uint8 - handle both float [0,1] and uint8 [0,255] ranges
            if image_array.dtype != np.uint8:
                # Convert from float [0,1] to uint8 [0,255]
                image_array = (image_array.clip(0.0, 1.0) * 255).astype(np.uint8)
            else:
                # If already uint8, ensure values are in valid range [0, 255]
                image_array = image_array.clip(0, 255).astype(np.uint8)
            h, w, c = image_array.shape
            # Flip vertically for Kivy (Kivy uses bottom-left origin)
            image_array = np.flipud(image_array)
            # Create texture
            texture = Texture.create(size=(w, h), colorfmt="rgb")
            texture.blit_buffer(
                image_array.tobytes(), colorfmt="rgb", bufferfmt="ubyte"
            )
            image_widget = self.image_canvas[row][col]["image"]
            image_widget.texture = texture
        elif isinstance(image_array_original, str):
            # Display text in title label
            title_label = self.image_canvas[row][col]["title"]
            title_label.text = image_array_original
            # Clear image
            image_widget = self.image_canvas[row][col]["image"]
            image_widget.texture = None
        if not isinstance(image_array_original, np.ndarray):
            image_array = image_array_original
            if MPL_SUPPORT and isinstance(image_array, Curve):
                # Render matplotlib plot to texture
                fig, ax = plt.subplots(figsize=(6, 4))
                image_array.create_plot(ax=ax)
                buf = BytesIO()
                fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
                buf.seek(0)
                plt.close(fig)
                # Convert to numpy array and create texture
                img = PILImage.open(buf)
                img_array = np.array(img)
                h, w = img_array.shape[:2]
                if len(img_array.shape) == 2:
                    # Grayscale
                    texture = Texture.create(size=(w, h), colorfmt="luminance")
                    texture.blit_buffer(
                        img_array.tobytes(), colorfmt="luminance", bufferfmt="ubyte"
                    )
                else:
                    # RGB
                    texture = Texture.create(size=(w, h), colorfmt="rgb")
                    texture.blit_buffer(
                        img_array.tobytes(), colorfmt="rgb", bufferfmt="ubyte"
                    )
                image_widget = self.image_canvas[row][col]["image"]
                image_widget.texture = texture
                buf.close()
        title_label = self.image_canvas[row][col]["title"]
        title_label.text = self.get_current_style(row, col).get("title", "")

    @staticmethod
    def convert_image(out_im):
        if isinstance(out_im, np.ndarray) and len(out_im.shape) > 1:
            # Handle both float [0,1] and uint8 [0,255] ranges
            if out_im.dtype != np.uint8:
                # Convert from float [0,1] to uint8 [0,255]
                return (out_im.clip(0.0, 1.0) * 255).astype(np.uint8)
            else:
                # If already uint8, ensure values are in valid range [0, 255]
                return out_im.clip(0, 255).astype(np.uint8)
        else:
            return out_im

    def refresh(self):
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)

    def reset_sliders(self):
        for widget_idx, ctrl in self.ctrl.items():
            if widget_idx in self.widget_list.keys():
                self.widget_list[widget_idx].reset()
        self.refresh()
