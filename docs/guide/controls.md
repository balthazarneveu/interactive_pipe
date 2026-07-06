# Controls

A control binds a GUI widget to a filter keyword argument. Declare controls in the `@interactive()` decorator; the widget type is inferred from the default value's type and the presence of a range.

## Declaration patterns

| You want | Declaration | Widget |
|---|---|---|
| Float slider | `gain=(1.0, [0.5, 2.0])` | slider with 1/100-range step |
| Float slider, custom label | `gain=(1.0, [0.5, 2.0], "exposure")` | slider labelled "exposure" |
| Int slider | `size=(5, [1, 15])` | slider with step 1 |
| Checkbox | `flip=(True,)` or `flip=Control(True)` | tick box |
| Dropdown | `mode=(["dark", "light"])` | menu, first element is the default |
| Dropdown, explicit default | `mode=("light", ["dark", "light"])` | menu defaulting to "light" |
| Key binding instead of widget | `flip=(True, "flip", "k")` | press ++k++ to toggle |
| Free text box | `TextPrompt("Hello world!")` | text entry |
| Circular slider (Qt) | `CircularControl(90, [0, 360], modulo=True)` | rotary dial |
| Key-driven value | `KeyboardControl(...)` | see [Keyboard](keyboard.md) |
| Animated timer | `TimeControl(update_interval_ms=50)` | auto-incrementing time |

The tuple shorthand `(default, [min, max], name)` is equivalent to `Control(default, [min, max], name=name)`. Use `Control` objects when you need the extra arguments (`step`, `icons`, `group`, `tooltip`):

```python
from interactive_pipe import interactive, Control

@interactive(
    gain=Control(1.0, [0.5, 2.0], name="exposure", step=0.05, tooltip="scene brightness"),
)
def exposure(img, gain=1.0):
    return img * gain
```

See the [Control API reference](../api/controls.md) for every argument.

## Slider range shorthand

`@interactive(blend_coeff=[0., 1.])` — a bare range creates a slider initialized to the middle of the range.

## Image buttons (Qt)

A string dropdown can be rendered as image buttons by providing one icon per choice:

```python
@interactive(song=Control("song_a", ["song_a", "song_b"], icons=["a.png", "b.png"]))
def choose_song(song="song_a"):
    ...
```

This is how the [jukebox demo](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox_demo.py) works.

## Grouping controls

Pass `group="Panel name"` (or a [`Panel`](panels.md) instance) to gather related controls together in the GUI.

## Decorating without `@`

Applying the decorator "from outside" keeps your library free of interactive_pipe imports:

```python
from core_filters import processing_block
from interactive_pipe import interactive

interactive(angle=(0., [-360., 360.]))(processing_block)
```
