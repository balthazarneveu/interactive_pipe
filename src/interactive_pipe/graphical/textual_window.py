import numpy as np
import logging
from typing import Optional, Union, Tuple, List
from interactive_pipe.graphical.window import InteractivePipeWindow
from interactive_pipe.headless.control import Control
from interactive_pipe.headless.keyboard import KeyboardControl
from interactive_pipe.graphical.textual_control import ControlFactory
from interactive_pipe.data_objects.curves import Curve

try:
    from textual.widgets import Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    logging.warning("Textual is not available. Install with: pip install textual")

try:
    from PIL import Image as PILImage

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None

# Try to import textual-image for better image display
try:
    from textual_image.renderable import Image as TextualImageRenderable

    TEXTUAL_IMAGE_AVAILABLE = True
except ImportError:
    TEXTUAL_IMAGE_AVAILABLE = False
    TextualImageRenderable = None


class TextualWindow(InteractivePipeWindow):
    """Textual-based window for displaying pipeline outputs and controls"""

    def __init__(
        self,
        controls: List[Control] = [],
        name: str = "",
        pipeline=None,
        size: Optional[Union[str, int, Tuple[int, int]]] = None,
        main_gui=None,
        **kwargs,
    ):
        if not TEXTUAL_AVAILABLE:
            raise ImportError(
                "Textual is not available. Install with: pip install textual"
            )

        super().__init__(name=name, pipeline=pipeline, size=size)
        self.controls = controls
        self.main_gui = main_gui
        self.pipeline.global_params["__window"] = self
        self.ctrl = {}
        self.control_widgets = {}
        self.image_canvas = None
        self._size = size

        # Initialize the Textual app structure
        self.app = None
        self.screen = None

    def add_image_placeholder(self, row, col):
        """Add a placeholder for an image at the given row/col position"""
        if self.image_canvas is None:
            return

        # Create a Static widget to hold the image
        # We'll update it with actual image data in update_image
        if self.image_canvas[row][col] is None:
            placeholder = Static("", id=f"image_{row}_{col}")
            self.image_canvas[row][col] = {"widget": placeholder, "data": None}

            # Add to image grid if available
            if hasattr(self, "image_grid") and self.image_grid:
                self.image_grid.mount(placeholder)

    def delete_image_placeholder(self, img_widget):
        """Remove an image placeholder"""
        if img_widget and "widget" in img_widget:
            widget = img_widget.get("widget")
            if widget is not None:
                # Widget removal will be handled by Textual's layout system
                pass

    def update_image(self, image_array, row, col):
        """Update the image displayed at row, col"""
        if self.image_canvas is None:
            return

        img_dict = self.image_canvas[row][col]
        # Handle case where image_canvas might contain numpy arrays or other types
        if img_dict is None or not isinstance(img_dict, dict):
            # Initialize as dict if it's not already one
            self.image_canvas[row][col] = {"widget": None, "data": None}
            img_dict = self.image_canvas[row][col]

        img = self.convert_image(image_array)
        current_style = self.get_current_style(row, col)

        # Handle different image types
        if isinstance(img, np.ndarray):
            if len(img.shape) > 1:
                # 2D image - convert to PIL and display
                pil_img = self._numpy_to_pil(img)
                if pil_img:
                    try:
                        # Try to use textual-image for better image display
                        title = current_style.get("title", f"Image {row}x{col}")
                        use_textual_image = False
                        image_method = "unknown"

                        if TEXTUAL_IMAGE_AVAILABLE and TextualImageRenderable:
                            try:
                                # Use textual-image renderable - it can accept PIL Image directly!
                                # Let textual-image auto-size or use minimal constraints to maintain aspect ratio
                                # Get original image dimensions (PIL returns width, height)
                                img_width, img_height = pil_img.size
                                img_aspect = (
                                    img_width / img_height
                                )  # width/height ratio

                                try:
                                    import shutil

                                    term_cols, term_rows = shutil.get_terminal_size()
                                    # Use terminal's actual dimensions, respecting its aspect ratio
                                    # Leave some margin for controls
                                    margin_cols = 10
                                    margin_rows = 15
                                    avail_width = term_cols - margin_cols
                                    avail_height = term_rows - margin_rows

                                    # Apply reasonable maximums, but maintain terminal's aspect ratio
                                    # Don't force a 2:1 ratio - use the terminal's natural ratio
                                    max_term_width = 300
                                    max_term_height = 150

                                    # Scale down if terminal is larger than max, but maintain ratio
                                    if avail_width > max_term_width:
                                        scale_term = max_term_width / avail_width
                                        avail_width = max_term_width
                                        avail_height = int(avail_height * scale_term)
                                    if avail_height > max_term_height:
                                        scale_term = max_term_height / avail_height
                                        avail_height = max_term_height
                                        avail_width = int(avail_width * scale_term)

                                    # Scale to fit while maintaining aspect ratio
                                    # Calculate scale factors for both dimensions
                                    scale_w = avail_width / img_width
                                    scale_h = avail_height / img_height
                                    # Use the smaller scale to ensure image fits in both dimensions
                                    scale = min(scale_w, scale_h)

                                    # Calculate final dimensions maintaining aspect ratio
                                    calc_width = int(img_width * scale)
                                    calc_height = int(img_height * scale)

                                    # Apply minimum size, but recalculate to maintain aspect ratio
                                    min_width = 120
                                    min_height = 60

                                    # If calculated size is below minimum, scale up proportionally
                                    if (
                                        calc_width < min_width
                                        or calc_height < min_height
                                    ):
                                        # Calculate scale needed to reach minimum
                                        scale_w_min = min_width / img_width
                                        scale_h_min = min_height / img_height
                                        # Use larger scale to ensure both dimensions meet minimum
                                        scale_min = max(scale_w_min, scale_h_min)
                                        # But don't exceed available space
                                        scale = min(scale, scale_min)
                                        # Recalculate with new scale
                                        calc_width = int(img_width * scale)
                                        calc_height = int(img_height * scale)

                                    max_width = calc_width
                                    max_height = calc_height
                                except Exception:
                                    # Fallback - use high quality defaults with correct aspect ratio
                                    max_size = 200
                                    # Maintain aspect ratio: if width is larger dimension, use it as base
                                    if img_width >= img_height:
                                        max_width = max_size
                                        max_height = int(max_size / img_aspect)
                                    else:
                                        max_height = max_size
                                        max_width = int(max_size * img_aspect)

                                # Create the renderable with both width and height to maintain aspect ratio
                                # Specify both dimensions to ensure correct aspect ratio
                                image_renderable = TextualImageRenderable(
                                    pil_img, width=max_width, height=max_height
                                )

                                # Create a Static widget to display the renderable
                                # Static widgets can display Rich renderables
                                from textual.widgets import Static

                                if img_dict.get("widget") is None:
                                    # Create Static widget with the image renderable and title
                                    # Combine title and image in a single Static widget
                                    if title:
                                        # Use Rich Text to combine title and image
                                        # The image renderable will be rendered by Rich
                                        # We'll use a Static widget that can display Rich renderables
                                        # For now, just use the image renderable directly
                                        image_widget = Static(
                                            image_renderable, id=f"image_{row}_{col}"
                                        )
                                    else:
                                        image_widget = Static(
                                            image_renderable, id=f"image_{row}_{col}"
                                        )

                                    img_dict["widget"] = image_widget
                                    img_dict["data"] = pil_img

                                    # Mount widget to grid
                                    if hasattr(self, "image_grid") and self.image_grid:
                                        try:
                                            self.image_grid.mount(
                                                image_widget, row=row, col=col
                                            )
                                        except Exception:
                                            self.image_grid.mount(image_widget)
                                else:
                                    # Update existing widget - replace the image renderable
                                    existing_widget = img_dict.get("widget")
                                    if existing_widget and isinstance(
                                        existing_widget, Static
                                    ):
                                        # Calculate size again (in case terminal size changed)
                                        # Use same logic as above for consistency
                                        img_width, img_height = pil_img.size
                                        img_aspect = img_width / img_height

                                        try:
                                            import shutil

                                            term_cols, term_rows = (
                                                shutil.get_terminal_size()
                                            )
                                            # Use terminal's actual dimensions, respecting its aspect ratio
                                            # Leave some margin for controls
                                            margin_cols = 10
                                            margin_rows = 15
                                            avail_width = term_cols - margin_cols
                                            avail_height = term_rows - margin_rows

                                            # Apply reasonable maximums, but maintain terminal's aspect ratio
                                            # Don't force a 2:1 ratio - use the terminal's natural ratio
                                            max_term_width = 300
                                            max_term_height = 150

                                            # Scale down if terminal is larger than max, but maintain ratio
                                            if avail_width > max_term_width:
                                                scale_term = (
                                                    max_term_width / avail_width
                                                )
                                                avail_width = max_term_width
                                                avail_height = int(
                                                    avail_height * scale_term
                                                )
                                            if avail_height > max_term_height:
                                                scale_term = (
                                                    max_term_height / avail_height
                                                )
                                                avail_height = max_term_height
                                                avail_width = int(
                                                    avail_width * scale_term
                                                )

                                            # Scale to fit while maintaining aspect ratio
                                            scale_w = avail_width / img_width
                                            scale_h = avail_height / img_height
                                            scale = min(scale_w, scale_h)

                                            calc_width = int(img_width * scale)
                                            calc_height = int(img_height * scale)

                                            # Apply minimum size, but recalculate to maintain aspect ratio
                                            min_width = 120
                                            min_height = 60

                                            # If calculated size is below minimum, scale up proportionally
                                            if (
                                                calc_width < min_width
                                                or calc_height < min_height
                                            ):
                                                # Calculate scale needed to reach minimum
                                                scale_w_min = min_width / img_width
                                                scale_h_min = min_height / img_height
                                                # Use larger scale to ensure both dimensions meet minimum
                                                scale_min = max(
                                                    scale_w_min, scale_h_min
                                                )
                                                # But don't exceed available space
                                                scale = min(scale, scale_min)
                                                # Recalculate with new scale
                                                calc_width = int(img_width * scale)
                                                calc_height = int(img_height * scale)

                                            max_width = calc_width
                                            max_height = calc_height
                                        except Exception:
                                            max_size = 200
                                            # Maintain aspect ratio: if width is larger dimension, use it as base
                                            if img_width >= img_height:
                                                max_width = max_size
                                                max_height = int(max_size / img_aspect)
                                            else:
                                                max_height = max_size
                                                max_width = int(max_size * img_aspect)

                                        # Create new renderable with both dimensions to maintain aspect ratio
                                        new_renderable = TextualImageRenderable(
                                            pil_img, width=max_width, height=max_height
                                        )
                                        existing_widget.update(new_renderable)
                                    img_dict["data"] = pil_img

                                use_textual_image = True
                                image_method = "textual-image (graphics protocol)"

                            except Exception as e:
                                logging.debug(f"Could not use textual-image: {e}")
                                image_method = (
                                    f"textual-image failed: {e}, using Unicode art"
                                )
                                # Fall back to Unicode art

                        if not use_textual_image:
                            if image_method == "unknown":
                                image_method = (
                                    "Unicode art (textual-image not available)"
                                )
                            # Fallback: Create high-resolution colored Unicode art representation
                            # Use higher resolution for better quality
                            display_width = 80  # Increased from 40
                            display_height = 40  # Increased from 20

                            try:
                                # Resize PIL image for display
                                small_img = pil_img.resize(
                                    (display_width, display_height),
                                    PILImage.Resampling.LANCZOS,
                                )
                                # Ensure RGB mode for color
                                if small_img.mode != "RGB":
                                    small_img = small_img.convert("RGB")

                                # Create colored text representation using Rich Text
                                from rich.text import Text

                                pixels = small_img.load()
                                colored_lines = []
                                for y in range(display_height):
                                    line_text = Text()
                                    for x in range(display_width):
                                        # Get pixel RGB values
                                        r, g, b = pixels[x, y]
                                        # Calculate brightness for character selection
                                        brightness = (r + g + b) / 3

                                        # Use better character set for smoother gradients
                                        # Using half-block characters for better detail
                                        if brightness < 16:
                                            char = " "
                                        elif brightness < 32:
                                            char = "░"
                                        elif brightness < 48:
                                            char = "▒"
                                        elif brightness < 64:
                                            char = "▓"
                                        elif brightness < 80:
                                            char = "█"
                                        elif brightness < 112:
                                            char = "█"
                                        elif brightness < 144:
                                            char = "█"
                                        elif brightness < 176:
                                            char = "█"
                                        elif brightness < 208:
                                            char = "█"
                                        else:
                                            char = "█"

                                        # Add character with RGB color using foreground color
                                        # Rich uses format: rgb(r,g,b) or #rrggbb
                                        hex_color = f"#{r:02x}{g:02x}{b:02x}"
                                        line_text.append(char, style=hex_color)
                                    colored_lines.append(line_text)

                                # Create a single Rich Text object with all lines
                                # Combine title and colored image
                                full_text = Text(f"{title}\n", style="bold")
                                # Add method indicator (subtle)
                                full_text.append(
                                    f"[{image_method}]\n", style="dim italic"
                                )
                                for line in colored_lines:
                                    full_text.append_text(line)
                                    full_text.append("\n")
                                full_text.append(f"Shape: {img.shape}", style="dim")

                                text_repr = full_text

                            except Exception as e:
                                logging.debug(
                                    f"Could not create colored visual representation: {e}"
                                )
                                # Fallback to simple text
                                text_repr = f"{title}\nShape: {img.shape}\nRange: [{img.min():.3f}, {img.max():.3f}]"

                            if img_dict.get("widget") is None:
                                text_widget = Static(text_repr, id=f"image_{row}_{col}")
                                img_dict["widget"] = text_widget
                                img_dict["data"] = pil_img
                                # Add to layout if we have a reference to the grid
                                if hasattr(self, "image_grid") and self.image_grid:
                                    try:
                                        self.image_grid.mount(
                                            text_widget, row=row, col=col
                                        )
                                    except Exception:
                                        self.image_grid.mount(text_widget)
                            else:
                                img_dict["widget"].update(text_repr)
                                img_dict["data"] = pil_img
                    except Exception as e:
                        logging.warning(f"Could not display image: {e}")
                        # Fallback to text representation
                        title = current_style.get("title", f"Image {row}x{col}")
                        text_repr = f"{title}\n{img.shape}"
                        if img_dict.get("widget") is None:
                            text_widget = Static(text_repr)
                            img_dict["widget"] = text_widget
                        else:
                            img_dict["widget"].update(text_repr)
                    else:
                        # Update existing widget
                        try:
                            img_dict["data"] = pil_img
                            # Textual Image widget doesn't support direct update
                            # We'll need to recreate or use a different approach
                            pass
                        except Exception as e:
                            logging.warning(f"Could not update image: {e}")
            elif len(img.shape) == 1:
                # 1D signal - display as text or use Curve
                text_repr = f"Signal: {len(img)} points\nMin: {img.min():.3f}, Max: {img.max():.3f}"
                if img_dict.get("widget") is None:
                    text_widget = Static(text_repr)
                    img_dict["widget"] = text_widget
                else:
                    img_dict["widget"].update(text_repr)
        elif isinstance(img, Curve):
            # For Curve objects, display as text representation
            text_repr = f"Curve: {len(img.curves)} curves"
            if img_dict.get("widget") is None:
                text_widget = Static(text_repr)
                img_dict["widget"] = text_widget
            else:
                img_dict["widget"].update(text_repr)
        elif isinstance(img, str):
            # String output
            if img_dict.get("widget") is None:
                text_widget = Static(img)
                img_dict["widget"] = text_widget
            else:
                img_dict["widget"].update(img)

        # Update title if available
        title = current_style.get("title", "")
        if title and img_dict.get("widget"):
            # Textual widgets can have titles via their ID or label
            pass

    def _numpy_to_pil(self, img_array: np.ndarray):
        """Convert numpy array to PIL Image"""
        if not PIL_AVAILABLE or PILImage is None:
            return None
        try:
            # Ensure image is in [0, 1] range and convert to uint8
            img_clipped = np.clip(img_array, 0.0, 1.0)
            if img_clipped.max() <= 1.0:
                img_uint8 = (img_clipped * 255).astype(np.uint8)
            else:
                img_uint8 = img_clipped.astype(np.uint8)

            # Handle grayscale vs RGB
            if len(img_uint8.shape) == 2:
                # Grayscale
                return PILImage.fromarray(img_uint8, mode="L")
            elif len(img_uint8.shape) == 3:
                if img_uint8.shape[2] == 3:
                    # RGB
                    return PILImage.fromarray(img_uint8, mode="RGB")
                elif img_uint8.shape[2] == 4:
                    # RGBA
                    return PILImage.fromarray(img_uint8, mode="RGBA")

            return None
        except Exception as e:
            logging.warning(f"Failed to convert numpy to PIL: {e}")
            return None

    def convert_image(self, img):
        """Convert image to displayable format"""
        if isinstance(img, np.ndarray) and len(img.shape) > 1:
            return img.clip(0.0, 1.0)
        else:
            return img

    def init_sliders(self, controls: List[Control]):
        """Initialize control widgets"""
        control_factory = ControlFactory()

        for ctrl in controls:
            slider_name = ctrl.name
            if isinstance(ctrl, KeyboardControl):
                if self.main_gui:
                    self.main_gui.bind_keyboard_slider(ctrl, self.key_update_parameter)
                continue

            # Skip single-value controls
            if (
                ctrl._type == str
                and ctrl.value_range is not None
                and len(ctrl.value_range) == 1
            ):
                continue

            self.ctrl[slider_name] = ctrl
            control_instance = control_factory.create_control(
                ctrl, self.update_parameter
            )
            if control_instance is not None:
                widget = control_instance.create()
                self.control_widgets[slider_name] = widget

    def update_parameter(self, idx, value):
        """Update parameter when control changes"""
        if idx in self.ctrl:
            self.ctrl[idx].update(value)
            self.refresh()

    def key_update_parameter(self, idx, down):
        """Update parameter from keyboard control"""
        if idx in self.ctrl:
            if down:
                self.ctrl[idx].on_key_down()
            else:
                self.ctrl[idx].on_key_up()
            self.refresh()

    def set_image_canvas(self, image_grid):
        """Override to initialize with None instead of numpy empty array"""
        expected_image_canvas_shape = (
            len(image_grid),
            max([len(image_row) for image_row in image_grid]),
        )
        # Check if the layout has been updated!
        self.check_image_canvas_changes(expected_image_canvas_shape)
        if self.image_canvas is None:
            # Initialize with None values, not numpy empty array (which fills with 0.0)
            nrows, ncols = expected_image_canvas_shape
            self.image_canvas = [[None for _ in range(ncols)] for _ in range(nrows)]

            # Set up grid layout if we have image_grid reference
            if hasattr(self, "image_grid") and self.image_grid:
                # Configure grid with proper rows and columns
                self.image_grid.grid_size_columns = ncols
                self.image_grid.grid_size_rows = nrows

            for row, image_row in enumerate(image_grid):
                for col, image_array in enumerate(image_row):
                    if image_array is None:
                        self.image_canvas[row][col] = None
                        continue
                    else:
                        self.add_image_placeholder(row, col)

    def refresh(self):
        """Refresh the display"""
        if self.pipeline is not None:
            try:
                out = self.pipeline.run()
                self.refresh_display(out)
            except Exception as e:
                # Log error but don't crash the app
                logging.error(f"Error during pipeline refresh: {e}", exc_info=True)
                # Show error in UI if possible
                if hasattr(self, "image_grid") and self.image_grid:
                    try:
                        error_widget = Static(f"Error: {str(e)}", id="pipeline_error")
                        self.image_grid.mount(error_widget)
                    except Exception:
                        pass

    def reset_sliders(self):
        """Reset all sliders to default values"""
        for widget_name, widget in self.control_widgets.items():
            if widget_name in self.ctrl:
                ctrl = self.ctrl[widget_name]
                if hasattr(widget, "_ctrl"):
                    # Update the control's value first
                    ctrl.value = ctrl.value_default
                if hasattr(widget, "value"):
                    # Handle different widget types
                    if hasattr(widget, "_ctrl") and widget._ctrl._type in [int, float]:
                        # Input widget for numeric types
                        widget.value = str(ctrl.value_default)
                    elif (
                        hasattr(widget, "_ctrl")
                        and widget._ctrl._type == str
                        and widget._ctrl.value_range is not None
                    ):
                        # Select widget - need to find the option tuple
                        if hasattr(widget, "options"):
                            for opt in widget.options:
                                if (
                                    isinstance(opt, tuple)
                                    and opt[0] == ctrl.value_default
                                ):
                                    widget.value = opt
                                    break
                    else:
                        widget.value = ctrl.value_default
                elif hasattr(widget, "set_value"):
                    widget.set_value(ctrl.value_default)
        self.refresh()
