# Controls

A control binds a GUI widget to a filter keyword argument. Declare controls in the `@interactive()` decorator; the widget type is inferred from the default value's type and the presence of a range.

## Two equivalent styles

The same control can always be written as a **tuple shorthand** — great for prototyping — or as an **explicit object** — clearer in larger codebases and required for the extra arguments (`step`, `icons`, `tooltip`, ...):

=== "Tuple shorthand"

    ```python
    from interactive_pipe import interactive

    @interactive(gain=(1.0, [0.5, 2.0], "exposure"))
    def exposure(img, gain=1.0):
        return img * gain
    ```

    The tuple order is `(default, range, name, group)` — trailing elements are optional.

=== "Explicit object"

    ```python
    from interactive_pipe import interactive, Control

    @interactive(gain=Control(1.0, [0.5, 2.0], name="exposure"))
    def exposure(img, gain=1.0):
        return img * gain
    ```

    `Control` unlocks every option: `Control(1.0, [0.5, 2.0], name="exposure", step=0.05, group="Panel A", tooltip="scene brightness")`.

!!! tip "Even shorter"
    A bare range works too: `@interactive(blend_coeff=[0., 1.])` creates a slider initialized to the middle of the range, and `@interactive(mode=["dark", "light"])` a dropdown defaulting to the first choice.

Specialized widgets (keyboard, circular slider, timer) only exist as explicit objects.

## Declaration patterns

| You want | Tuple shorthand | Explicit object |
|---|---|---|
| Float slider | `gain=(1.0, [0.5, 2.0])` | `gain=Control(1.0, [0.5, 2.0])` |
| ... with a custom label | `gain=(1.0, [0.5, 2.0], "exposure")` | `gain=Control(1.0, [0.5, 2.0], name="exposure")` |
| Int slider (step 1) | `size=(5, [1, 15])` | `size=Control(5, [1, 15])` |
| Checkbox | `flip=(True,)` | `flip=Control(True)` |
| Dropdown | `mode=("light", ["dark", "light"])` | `mode=Control("light", ["dark", "light"])` |
| Dropdown, first choice as default | `mode=["dark", "light"]` | — |
| Free text box | `txt=("Hello world!", None)` | `txt=TextPrompt("Hello world!")` |
| Grouped in a panel | `gain=(1.0, [0.5, 2.0], "gain", "Panel A")` | `gain=Control(1.0, [0.5, 2.0], group="Panel A")` |
| Key-driven value ([Keyboard](keyboard.md)) | — | `idx=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True)` |
| Circular slider (Qt) | — | `angle=CircularControl(90, [0, 360], modulo=True)` |
| Animated timer | — | `t=TimeControl(update_interval_ms=50)` |

See the [Control API reference](../api/controls.md) for every argument.

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
