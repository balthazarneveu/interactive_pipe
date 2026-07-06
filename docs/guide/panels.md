# Panels

Panels group controls into visual sections. The simplest form is the `group=` argument of a control:

```python
from interactive_pipe import interactive, Control

@interactive(
    brightness=Control(1.0, [0.0, 2.0], group="Color Adjustments"),
    contrast=Control(1.0, [0.5, 1.5], group="Color Adjustments"),
)
def adjust(img, brightness=1.0, contrast=1.0):
    ...
```

Controls sharing the same group name land in the same panel — even across different filters (same-named string groups share one panel process-wide).

## Panel objects

For fine control — nesting, grids, collapsing, positioning — build `Panel` instances:

```python
from interactive_pipe import Panel

text_panel = Panel("Text Settings", collapsible=True)
color_panel = Panel("Color Adjustments", collapsible=True)
effects_panel = Panel("Effects", collapsible=True, collapsed=False)

# Nested structure with a grid layout: two panels side by side, one full width
main_panel = Panel("Processing Controls").add_elements(
    [
        [text_panel, color_panel],  # row 1
        [effects_panel],            # row 2
    ]
)

@interactive(font_size=Control(12, [6, 48], group=text_panel))
def add_caption(img, font_size=12):
    ...
```

Features (Qt backend has the fullest support, gradio supports collapsible panels):

- **Nesting**: panels contain sub-panels via `add_elements`, with row-based grid layouts.
- **Collapsible**: `collapsible=True`, optionally starting `collapsed=True`.
- **Positioning**: place the control panel left, right, top or bottom of the images.
- **Detached panels**: pop the controls out into a separate window.

## Demos

- [panel_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/panel_demo.py) — nesting, grids, collapsing
- [grouped_controls_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/grouped_controls_demo.py) — string groups
- [panel_position_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/panel_position_demo.py) — positioning
- [detached_panel_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/detached_panel_demo.py) — separate control window

Full reference: [`Panel`](../api/controls.md).
