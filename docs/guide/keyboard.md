# Keyboard

## GUI shortcuts

Built-in shortcuts while using the GUI (Qt, Dear PyGui and matplotlib backends):

- ++f1++ show the help shortcuts in the terminal
- ++f11++ toggle fullscreen mode
- ++w++ write full resolution image to disk
- ++r++ reset parameters
- ++i++ print parameters dictionary in the command line
- ++e++ export parameters dictionary to a yaml file
- ++o++ import parameters dictionary from a yaml file (sliders update)
- ++g++ export a pipeline diagram (requires graphviz)
- ++q++ quit

++e++, ++o++ and ++w++ ask for the file path with a native file dialog on Qt and Dear PyGui (cancel does nothing); matplotlib asks in the terminal (empty input cancels). ++e++ suggests `<name>_tuning.yaml`.

## Menu bar

Qt and Dear PyGui expose every action above in a menu bar, with the shortcut shown next to each entry:

- **File**: save images (++w++), export tuning (++e++), import tuning (++o++), quit (++q++)
- **View**: toggle fullscreen (++f11++)
- **Pipeline**: reset parameters (++r++), print parameters (++i++), show graph (++g++)
- **Help**: keyboard shortcuts (++f1++)

Menu entries and keys run the same action, so rebinding a key (`bind_key`) never changes what a menu entry does. Matplotlib has no menu bar and keeps the shortcuts. Keys, menus and the ++f1++ help are all generated from one table in `interactive_pipe/graphical/actions.py`.

## KeyboardControl

A `KeyboardControl` behaves exactly like a slider internally, but is driven by key presses instead of a widget:

```python
from interactive_pipe import interactive, KeyboardControl

@interactive(
    image_index=KeyboardControl(0, [0, 2], keydown="pagedown", keyup="pageup", modulo=True)
)
def switch_image(img1, img2, img3, image_index=0):
    return [img1, img2, img3][image_index]
```

- `keydown` decreases the value (or toggles a bool), `keyup` increases it.
- `modulo=True` wraps around at the range bounds — here ++page-up++ past index 2 goes back to 0.
- Special keys: arrows, `"pageup"`/`"pagedown"`, spacebar, `"f1"`–`"f12"`; anything else is a single character.
- On backends without key events (gradio, notebook), a `KeyboardControl` maps back to a regular slider — no need to remove it.

Keyboard bindings always use the explicit `KeyboardControl` object — there is no tuple shorthand for them. A bool `KeyboardControl(True, keydown="k")` turns a checkbox into a ++k++ toggle.

## Key-bound one-shot events

For events that are not values — "trigger this on the next run" — bind a key to the context and read it through the read-only `events` proxy:

```python
from interactive_pipe import events, interactive

@interactive()
def noise_burst(img):
    if events.get("noise_burst"):  # True only on the run following the key press
        return add_noise(img)
    return img

demo = interactive_pipeline(gui="qt")(my_pipeline)
demo.pipeline.bind_key_to_context("n", "noise_burst", "one-shot noise burst")
```

See [demo/key_event_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/key_event_demo.py) for the full example.
