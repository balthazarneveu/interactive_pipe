from typing import List, Optional, Union, cast


class Panel:
    """Panel for organizing controls into groups with optional nesting and grid layouts.

    Panels can contain:
    - Controls (assigned via control.group=panel)
    - Other Panels (nested hierarchy)
    - Grid layouts (via list of lists)

    Example:
        # Simple panel
        text_panel = Panel("Text Settings")

        # Collapsible panel
        color_panel = Panel("Colors", collapsible=True, collapsed=False)

        # Detached panel (Qt backend only - opens in separate window)
        tools_panel = Panel("Tools", detached=True, detached_size=(400, 600))

        # Panel with position (left, right, top, or bottom)
        left_panel = Panel("Tools", position="left")
        right_panel = Panel("Settings", position="right")

        # Nested panels with grid layout
        main_panel = Panel("Main").add_elements([
            [text_panel, color_panel],  # Row 1: side by side
            [effects_panel],            # Row 2: full width
        ])
    """

    def __init__(
        self,
        name: Optional[str] = None,
        collapsible: bool = False,
        collapsed: bool = False,
        detached: bool = False,
        detached_size: Optional[tuple] = None,
        position: Optional[str] = None,
    ) -> None:
        """Initialize a Panel.

        Args:
            name: Display name for the panel (shown in group box title)
            collapsible: Whether the panel can be collapsed/expanded
            collapsed: Initial collapsed state (only used if collapsible=True)
            detached: Whether to render panel in a separate window (Qt backend only)
            detached_size: Optional (width, height) tuple for detached window size
            position: Position relative to images - "left", "right", "top", "bottom", or None (defaults to "bottom")
        """
        # Validate position
        valid_positions = {None, "left", "right", "top", "bottom"}
        if position not in valid_positions:
            raise ValueError(f"position must be one of {valid_positions}, got {position}")
        self.name = name
        self.collapsible = collapsible
        self.collapsed = collapsed
        self.detached = detached
        self.detached_size = detached_size
        self.position = position
        self.elements = []  # List of Panels or list of lists (grid)
        self.parent = None  # Parent panel in hierarchy
        self._controls = []  # Controls assigned to this panel

    def add_elements(self, elements: Union[List["Panel"], List[List["Panel"]]]):
        """Add child panels with optional grid layout.

        Args:
            elements: Can be:
                - List of Panels: [panel1, panel2] - vertical stack
                - List of lists: [[panel1, panel2], [panel3]] - grid layout

        Returns:
            self for method chaining

        Example:
            main_panel.add_elements([
                [text_panel, color_panel],  # Row 1
                [effects_panel],            # Row 2
            ])
        """
        self.elements = elements
        self._set_parent_refs()
        return self

    def _set_parent_refs(self) -> None:
        """Set parent references for all child panels."""
        if not self.elements:
            return

        # Check if grid layout (list of lists)
        if isinstance(self.elements[0], list):
            # Grid layout - cast to List[List[Panel]] for type checker
            grid_elements = cast(List[List["Panel"]], self.elements)
            for row in grid_elements:
                for panel in row:
                    if isinstance(panel, Panel):
                        panel.parent = self
        else:
            # Flat list - cast to List[Panel] for type checker
            flat_elements = cast(List["Panel"], self.elements)
            for panel in flat_elements:
                if isinstance(panel, Panel):
                    panel.parent = self

    def _register_control(self, control) -> None:
        """Called when a control is assigned to this panel.

        Args:
            control: The Control instance being registered
        """
        if control not in self._controls:
            self._controls.append(control)

    def __repr__(self) -> str:
        name_str = f'"{self.name}"' if self.name else "None"
        controls_count = len(self._controls)
        elements_count = len(self.elements) if self.elements else 0
        detached_str = f", detached={self.detached}" if self.detached else ""
        position_str = f", position={self.position}" if self.position else ""
        return (
            f"Panel(name={name_str}, collapsible={self.collapsible}, "
            f"collapsed={self.collapsed}{detached_str}{position_str}, "
            f"controls={controls_count}, elements={elements_count})"
        )

    def __eq__(self, other) -> bool:
        """Panels are equal if they're the same object (for deduplication)."""
        return self is other

    def __hash__(self) -> int:
        """Use object id for hashing (for set/dict usage)."""
        return id(self)

    def get_root(self) -> "Panel":
        """Get the root panel in the hierarchy (walks up parent chain)."""
        current = self
        while current.parent is not None:
            current = current.parent
        return current
