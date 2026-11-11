"""Reusable Qt widgets for the Qt GUI backend.

Import direction is one-way: qt_gui imports this module, never the reverse
(MainWindow is referenced only as a type annotation).
"""

from typing import TYPE_CHECKING, Callable, Optional

from interactive_pipe.graphical.qt_backend import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSize,
    Qt,
    QtFrameBase,
    QtWidgetBase,
    QVBoxLayout,
    QWidget,
)
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.headless.panel import Panel

if TYPE_CHECKING:
    from interactive_pipe.graphical.qt_gui import MainWindow


class ElidedLabel(QLabel):  # type: ignore[reportGeneralTypeIssues]
    """Label that shortens its lines with "…" instead of being cut or widening its column.

    Whenever it had to be elided, the full text is set as tooltip and handed to
    ``on_hover(text)`` when the mouse enters the label (``on_hover(None)`` when it
    leaves): tooltips do not show up reliably on every platform (Wayland), so
    the window also mirrors it in its status line.
    ``text()`` returns the text that was set; ``displayed_text()`` what is drawn.
    """

    def __init__(self, text: str = "", parent=None, on_hover: Optional[Callable[[Optional[str]], None]] = None):
        super().__init__(parent)
        self._full_text = ""
        self.on_hover = on_hover
        self.setText(text)

    def is_elided(self) -> bool:
        return self.displayed_text() != self._full_text

    def enterEvent(self, event):  # noqa: N802 (Qt API)
        super().enterEvent(event)
        if self.on_hover is not None and self.is_elided():
            self.on_hover(self._full_text)

    def leaveEvent(self, event):  # noqa: N802 (Qt API)
        super().leaveEvent(event)
        if self.on_hover is not None:
            self.on_hover(None)

    def text(self) -> str:
        return self._full_text

    def displayed_text(self) -> str:
        return super().text()

    def setText(self, text) -> None:  # noqa: N802 (Qt API)
        self._full_text = "" if text is None else str(text)
        self._refresh()
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802 (Qt API)
        metrics = self.fontMetrics()
        lines = self._full_text.split("\n") or [""]
        margins = self.contentsMargins()
        # +2: elidedText already trims a line whose advance equals the available width exactly
        width = max(metrics.horizontalAdvance(line) for line in lines) + margins.left() + margins.right() + 2
        height = metrics.lineSpacing() * len(lines) + margins.top() + margins.bottom()
        return QSize(width, height)

    def minimumSizeHint(self):  # noqa: N802 (Qt API)
        # any width is fine (the text gets elided), keep the height of the full text
        return QSize(0, self.sizeHint().height())

    def resizeEvent(self, event):  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        width = self.contentsRect().width()
        metrics = self.fontMetrics()
        lines = [
            line
            if metrics.horizontalAdvance(line) <= width
            else metrics.elidedText(line, Qt.TextElideMode.ElideRight, width)
            for line in self._full_text.split("\n")
        ]
        shown = "\n".join(lines)
        super().setText(shown)
        self.setToolTip(self._full_text if self.is_elided() else "")


class ControlsContent(QWidget):  # type: ignore[reportGeneralTypeIssues]
    """Content of a ControlsScrollArea. It is not laid out by the window, so
    its size changes (controls added, collapsed, spread over columns) are
    forwarded to the scroll area, or the window keeps a stale size hint.
    (An event filter on the scroll area would do it too, but Python event
    filters crash when the widgets are torn down.)"""

    def event(self, event):  # noqa: N802 (Qt API)
        if event.type() == event.Type.LayoutRequest:
            viewport = self.parentWidget()
            area = viewport.parentWidget() if viewport is not None else None
            if area is not None:
                area.updateGeometry()
        return super().event(event)


class ControlsScrollArea(QScrollArea):  # type: ignore[reportGeneralTypeIssues]
    """Vertical scroll area for the controls below the images.

    It asks for the full height of its content, so the controls show whole
    whenever there is room, but it shrinks down to ``MIN_HEIGHT`` and scrolls
    when the images take the room (1:1 view, small window).
    """

    MIN_HEIGHT = 60

    def __init__(self, content: QWidget, parent=None):
        super().__init__(parent)
        # narrowest width (None: the content's): the window sets it to a single
        # column of controls, so it can shrink and spread them over fewer columns
        self.minimum_width: Optional[int] = None
        self.setWidget(content)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        # QScrollArea caps its hint: the controls would scroll needlessly
        content = self.widget()
        if content is None:
            return QSize(0, 0)
        hint = content.sizeHint().expandedTo(content.minimumSizeHint())
        bar = self.verticalScrollBar()
        bar_width = bar.sizeHint().width() if bar is not None else 0
        return QSize(hint.width() + bar_width, hint.height())  # room for the bar: no horizontal clipping

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        hint = self.sizeHint()
        width = hint.width() if self.minimum_width is None else min(hint.width(), self.minimum_width)
        return QSize(width, min(hint.height(), self.MIN_HEIGHT))


class CollapsibleBox(QtFrameBase):  # type: ignore[reportGeneralTypeIssues]
    """Modern collapsible panel with smooth animation and arrow indicator."""

    def __init__(self, title="", collapsed=False, parent=None):
        super().__init__(parent)
        self.is_collapsed = collapsed

        # QFrame is better for borders and rounded corners
        # Set frame shape and shadow for proper border rendering
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setLineWidth(1)

        # Main layout
        self.main_layout = QVBoxLayout(self)
        # No margins - border will be on the frame itself
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Apply QGroupBox-like styling with rounded corners
        # QFrame renders border-radius better than QWidget
        # Only style the border, don't set background-color to avoid affecting child widgets
        self.setObjectName("collapsibleBox")
        self.setStyleSheet("""
            QFrame#collapsibleBox {
                border: 1px solid #c0c0c0;
                border-radius: 5px;
            }
        """)

        # Toggle button with arrow
        self.toggle_button = QPushButton(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(not collapsed)
        # Style button to not interfere with parent border visibility
        self.toggle_button.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px;
                border: none;
                background-color: #f0f0f0;
                font-weight: bold;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:checked {
                background-color: #d0d0d0;
            }
        """)
        self.toggle_button.clicked.connect(self.toggle)

        # Content area (no layout initially - will be set later)
        self.content_area = QWidget()
        # Don't set stylesheet on content area to avoid affecting slider colors

        # Add widgets to main layout
        self.main_layout.addWidget(self.toggle_button)
        self.main_layout.addWidget(self.content_area)

        # Set initial state
        if collapsed:
            self.content_area.setVisible(False)

        self.update_arrow()

    def update_arrow(self):
        """Update the arrow icon based on collapsed state."""
        arrow = "▼" if not self.is_collapsed else "▶"
        current_text = self.toggle_button.text()
        # Remove existing arrow if present
        if current_text.startswith("▼ ") or current_text.startswith("▶ "):
            current_text = current_text[2:]
        self.toggle_button.setText(f"{arrow} {current_text}")

    def toggle(self):
        """Toggle the collapsed state with smooth animation."""
        self.is_collapsed = not self.is_collapsed
        self.content_area.setVisible(not self.is_collapsed)
        self.update_arrow()

    def set_layout(self, layout):
        """Set the layout for the content area."""
        # Set margins on the layout for beautiful, balanced spacing
        layout.setContentsMargins(12, 12, 12, 12)
        # Set the layout (only called once, no existing layout)
        self.content_area.setLayout(layout)


class DetachedPanelWindow(QtWidgetBase):  # type: ignore[reportGeneralTypeIssues]
    """Detached window for rendering a panel separately from the main window."""

    def __init__(
        self,
        panel: Panel,
        main_window: "MainWindow",
        control_factory: ControlFactory,
        parent=None,
    ):
        """Initialize a detached panel window.

        Args:
            panel: The Panel to render in this window
            main_window: Reference to the main window for refresh callbacks
            control_factory: Factory for creating control widgets
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.panel = panel
        self.main_window = main_window
        self.control_factory = control_factory

        # Set window title from panel name
        self.setWindowTitle(panel.name or "Detached Panel")

        # Set window size if specified
        if panel.detached_size is not None:
            width, height = panel.detached_size
            self.setMinimumWidth(width)
            self.setMinimumHeight(height)

        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Build and add the panel widget
        panel_widget = main_window._build_panel_widget(panel, control_factory)
        self.main_layout.addWidget(panel_widget)

        # Show the window
        self.show()

    def closeEvent(self, event):
        """Handle window close event."""
        # Remove from main window's list of detached windows
        if self in self.main_window.detached_windows:
            self.main_window.detached_windows.remove(self)
        event.accept()
