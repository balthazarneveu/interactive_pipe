import logging
import sys
from typing import Any, List, Optional, Tuple

# display_kind / apply_display_style / HEATMAP_STYLE_KEYS are re-exported for compatibility
from interactive_pipe.graphical.display import (  # noqa: F401
    HEATMAP_STYLE_KEYS,
    DisplayError,
    apply_display_style,
    content_title,
    display_data,
    display_kind,
    figure_of,
    prepare_display,
    producer_of,
)


def content_titles(grid: Any) -> dict:
    """{(row, col): title} of the outputs carrying their own title (``Image``)."""
    titles = {}
    rows = grid if isinstance(grid, list) else [grid]
    for row, cells in enumerate(rows):
        for col, content in enumerate(cells if isinstance(cells, list) else [cells]):
            title = content_title(content)
            if title:
                titles[(row, col)] = title
    return titles


def format_run_status(report) -> str:
    """One-line summary of a RunReport for the status line, e.g.
    "run 12.3 ms · 3 filters · 1 cached" ("error in <filter>" when it failed)."""
    if report is None:
        return ""
    if report.failed is not None:
        return f"error in {report.failed}"
    return f"run {report.total * 1000:.1f} ms · {report.num_filters} filters · {len(report.cached)} cached"


def format_timings_table(report) -> List[str]:
    """Per-filter timings of a RunReport as text lines (filter, ms, cached flag, total)."""
    if report is None:
        return ["No pipeline run yet."]
    names = list(report.timings)
    width = max([len("filter")] + [len(name) for name in names])
    lines = [f"{'filter':<{width}}  {'ms':>9}  cached", "-" * (width + 19)]
    for name in names:
        flag = "FAILED" if name == report.failed else ("yes" if name in report.cached else "")
        lines.append(f"{name:<{width}}  {report.timings[name] * 1000:9.2f}  {flag}")
    lines.append("-" * (width + 19))
    if report.failed is not None:
        # the filters after the failing one never ran: not a full-run total
        lines.append(f"{'total':<{width}}  {report.total * 1000:9.2f}  (until the error)")
        lines.append(f"Run failed at {report.failed}: later filters did not run.")
    else:
        lines.append(f"{'total':<{width}}  {report.total * 1000:9.2f}")
    return lines


def format_error_message(error) -> str:
    """In-window text for a FilterError: "⚠ <filter> raised <ExcType>: <msg>"."""
    original = error.original_error
    return f"⚠ {error.filter_name} raised {type(original).__name__}: {original}"


class InteractivePipeWindow:
    """Display & refresh image results, hosts the sliders & allows refreshing layout grid.

    The window/figure displays the results & the sliders.
    `size = (w, h) | "fullscreen" | "maximized defines"` defines the user expected window size.
    - It deals with the graphical refresh
    - It allows to refreshes the canvas
    (displaying two images side by side or four images in a 2x2 square fashion for instance.)
    """

    def __init__(self, *args, name=None, pipeline=None, size=None, style=None, **kwargs) -> None:
        self.name = name
        self.image_canvas: Optional[List[List[Any]]] = None
        self._size = size
        if style is not None:
            logging.info("no support for style in Qt backend")
        self.pipeline = pipeline

    @property
    def window_size(self):
        """Requested window size: (w, h), "fullscreen"/"maximized" or None.

        Named window_size (not size) because Qt widgets already define size().
        """
        return self._size

    @window_size.setter
    def window_size(self, _size):
        self._size = _size

    def add_image_placeholder(self, row, col):
        raise NotImplementedError

    def delete_image_placeholder(self, img_widget):
        raise NotImplementedError

    def update_image(self, content, row, col):
        raise NotImplementedError

    def get_current_style(self, row, col):
        if self.pipeline is None:
            raise RuntimeError("Pipeline is not set")
        img_name = self.pipeline.outputs[row][col]
        return self.resolve_style(img_name, self.pipeline.framework_state.output_styles, row, col)

    def resolve_style(self, name: Any, styles: dict, row: int, col: int) -> dict:
        """Style of the output `name` shown in cell (row, col), with its title:
        ``layout.style(title=...)``, else the title carried by the output itself
        (``Image(..., title=...)``), else the output name."""
        style = dict(styles.get(name) or {})
        if "title" not in style:
            own_title = (getattr(self, "_content_titles", None) or {}).get((row, col))
            style["title"] = own_title if own_title else name
        return style

    def check_image_canvas_changes(self, expected_image_canvas_shape):
        if self.image_canvas is not None:
            current_canvas_shape = (
                len(self.image_canvas),
                max([len(image_row) for image_row in self.image_canvas]),
            )
            if current_canvas_shape != expected_image_canvas_shape:
                for row_content in self.image_canvas:
                    for img_widget in row_content:
                        if img_widget is not None:
                            self.delete_image_placeholder(img_widget)
                self.image_canvas = None
                logging.debug("Need to fully re-initialize canvas")

    def set_image_canvas(self, image_grid):
        expected_image_canvas_shape = (
            len(image_grid),
            max([len(image_row) for image_row in image_grid]),
        )
        # Check if the layout has been updated!
        self.check_image_canvas_changes(expected_image_canvas_shape)
        if self.image_canvas is None:
            # rectangular canvas: cells of short (jagged) rows and None outputs stay None
            nrows, ncols = expected_image_canvas_shape
            self.image_canvas = [[None] * ncols for _ in range(nrows)]
            for row, image_row in enumerate(image_grid):
                for col, image_array in enumerate(image_row):
                    if image_array is not None:
                        self.add_image_placeholder(row, col)

    def set_images(self, image_grid) -> None:
        self.set_image_canvas(image_grid)
        for row, image_row in enumerate(image_grid):
            for col, image_array in enumerate(image_row):
                if image_array is None:
                    continue
                if self.image_canvas[row][col] is None:  # type: ignore[index]
                    # the output was None when the canvas was built: its cell comes now
                    self.add_image_placeholder(row, col)
                self.update_image(image_array, row, col)

    def error_cell_positions(self, error) -> List[Tuple[int, int]]:
        """(row, col) of the cells showing outputs of the filter that raised
        (the first cell when none of them is displayed).

        Builds the canvas from the output names when the very first run failed.
        """
        outputs = self.pipeline.outputs if self.pipeline is not None else None
        if self.image_canvas is None and outputs:
            self.set_image_canvas(outputs)
        positions = [
            (row, col)
            for row, cells in enumerate(self.image_canvas or [])
            for col, cell in enumerate(cells)
            if cell is not None
        ]
        failing_outputs = set()
        for filt in getattr(self.pipeline, "filters", None) or []:
            if filt.name == error.filter_name:
                failing_outputs = set(filt.outputs or [])
        matching = []
        for row, col in positions:
            try:
                name = outputs[row][col]  # type: ignore[index]
            except (IndexError, TypeError):
                continue
            if name in failing_outputs:
                matching.append((row, col))
        return matching or positions[:1]

    def report_error(self, error) -> None:
        """Print a filter error shown in the window on the console, once.

        Nothing catches an error in a GUI event loop and the engine only
        raises, so the window prints it; the same error repeated on the next
        slider moves is not printed again until a run succeeds.
        """
        message = str(error)
        if self.__dict__.get("_reported_error") == message:
            return
        self._reported_error = message
        if hasattr(error, "print_compact"):
            error.print_compact()
        else:
            print(message, file=sys.stderr)

    def _styled(self, content: Any, row: int, col: int) -> Any:
        """Content as the backends should draw it, with its ``layout.style``
        display options applied (see ``graphical.display.prepare_display``)."""
        try:
            style = self.get_current_style(row, col)
        except (IndexError, KeyError, TypeError, RuntimeError):
            style = None
        name = filter_name = None
        try:
            name = self.pipeline.outputs[row][col]  # type: ignore[union-attr, index]
            filter_name = producer_of(getattr(self.pipeline, "filters", None), name)
        except (AttributeError, IndexError, KeyError, TypeError):
            pass
        errors = self.__dict__.setdefault("_display_errors", {})
        try:
            box = None
            if figure_of(display_data(content)) is not None:
                box = self._safe_figure_box(row, col)
                if box is None:
                    self.__dict__.setdefault("_unfitted_figures", set()).add((row, col))
            shown = prepare_display(content, style, name, filter_name, box, self.figure_pixel_ratio())
        except DisplayError as error:
            # shown in the cell as text (every backend draws text): the window keeps running;
            # logged once, not on every slider move
            message = str(error)
            if errors.get((row, col)) != message:
                logging.error(message)
            errors[(row, col)] = message
            return message  # each backend wraps text to its cell
        errors.pop((row, col), None)
        return shown

    def figure_box(self, row: int, col: int) -> Optional[Tuple[float, float]]:
        """(width, height) in logical pixels of the cell (row, col), where a
        matplotlib figure output is drawn at that size (text the size of a
        Curve's); None (the default) draws it at its own figsize."""
        return None

    def figure_pixel_ratio(self) -> float:
        """Device pixels per logical pixel of the cells (HiDPI screens)."""
        return 1.0

    def _safe_figure_box(self, row: int, col: int) -> Optional[Tuple[float, float]]:
        try:
            return self.figure_box(row, col)
        except (IndexError, KeyError, TypeError, AttributeError):  # cell not created yet
            return None

    def convert_image(self, img):
        """Convert image to backend-specific format. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement convert_image")

    def refresh_display(self, _out) -> None:
        self._reported_error = None  # a run succeeded: the next error is printed again
        if _out is None:
            logging.warning("No output to display")
            return
        # In case no canvas has been provided
        if isinstance(_out, tuple):
            _out = [list(_out)]
        self._content_titles = content_titles(_out)
        # Build a fresh grid of converted outputs: the pipeline results are left untouched
        # (no deep copy of the buffers - converting large images every frame is costly enough).
        out = []
        for row, img_row in enumerate(_out):
            if isinstance(img_row, list):
                out.append(
                    [
                        None if img is None else self.convert_image(self._styled(img, row, col))
                        for col, img in enumerate(img_row)
                    ]
                )
            else:
                out.append([self.convert_image(self._styled(img_row, row, 0))])
        logging.debug(f"{len(out)} x {max((len(row) for row in out), default=0)} figures")
        self.set_images(out)
        # figures shown before their cell existed: drawn again at the cell size, now known
        for row, col in sorted(self.__dict__.pop("_unfitted_figures", set())):
            if self._safe_figure_box(row, col) is not None:
                content = _out[row][col] if isinstance(_out[row], list) else _out[row]
                self.update_image(self.convert_image(self._styled(content, row, col)), row, col)
        self.__dict__.pop("_unfitted_figures", None)
