"""Reusable Qt widgets for the Qt GUI backend.

Import direction is one-way: qt_gui imports this module, never the reverse
(MainWindow is referenced only as a type annotation).
"""

from typing import TYPE_CHECKING

from interactive_pipe.graphical.qt_backend import (
    QFrame,
    QPushButton,
    QtFrameBase,
    QtWidgetBase,
    QVBoxLayout,
    QWidget,
)
from interactive_pipe.graphical.qt_control import ControlFactory
from interactive_pipe.headless.panel import Panel

if TYPE_CHECKING:
    from interactive_pipe.graphical.qt_gui import MainWindow


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
