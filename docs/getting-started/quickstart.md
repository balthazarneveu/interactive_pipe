# Quickstart

Let's define three very basic image processing filters — `exposure`, `black_and_white` and `blend` — and turn them into a GUI application.

By design:

- image buffer inputs are positional arguments,
- keyword arguments are the parameters that can be turned into interactive widgets,
- output buffers are simply returned, like in a regular function.

The `@interactive()` decorator declares which parameters become widgets. Parameters declared as a **tuple/list** in the decorator become sliders, tick boxes or dropdown menus: `@interactive(param=(default, [min, max], name))` creates a float slider, for instance.

Finally, the glue combining the filters is the pipeline function. Decorating it with `@interactive_pipeline(gui="qt")` means calling it magically opens a GUI-powered image processing pipeline.

```python
from interactive_pipe import interactive, interactive_pipeline
import numpy as np

@interactive(
    coeff=(1., [0.5, 2.], "exposure"),
    bias=(0., [-0.2, 0.2])
)
def exposure(img, coeff=1., bias=0.):
    """Multiplies by coeff & adds a constant bias to the image"""
    # In the GUI, coeff is labelled "exposure". The bias tuple has no
    # trailing string, so its widget is named after the keyword arg.
    return img * coeff + bias


@interactive(bnw=(True, "black and white"))
def black_and_white(img, bnw=True):
    """Averages the 3 color channels (Black & White) if bnw=True"""
    # Booleans: a tuple like (True,) creates the tick box.
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img


@interactive(blend_coeff=(0.5, [0., 1.]))
def blend(img0, img1, blend_coeff=0.5):
    """Blends between two images.
    - blend_coeff=0 -> image 0 [slider to the left ]
    - blend_coeff=1 -> image 1 [slider to the right]
    """
    return (1 - blend_coeff) * img0 + blend_coeff * img1


# you can change the backend to mpl instead of qt here.
@interactive_pipeline(gui="qt", size="fullscreen")
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended = blend(exposed, bnw_image)
    return exposed, blended, bnw_image

if __name__ == '__main__':
    input_image = np.array([0., 0.5, 0.8]) * np.ones((256, 512, 3))
    sample_pipeline(input_image)
```

❤️ This code displays a GUI with three images; the middle one is the result of the blend.

!!! warning "Pipeline functions contain only filter calls"
    The pipeline function body is analyzed statically to build the execution graph, so it may contain **only filter calls, assignments and a return** — no if/for/while, no arithmetic. Put that logic inside the filters.

Notes:

- With a bare `@interactive()` and `def blend(img0, img1, blend_coeff=0.5):`, `blend_coeff` simply won't get a slider.
- `@interactive(blend_coeff=[0., 1.])` creates a slider initialized to the middle of the range (0.5).
- `@interactive(bnw=(True, "black and white", "k"))` replaces the checkbox by a keypress event (press ++k++ to toggle).

## Keeping your library clean

You may not want interactive_pipe imported in your algorithm library at all. Keep the filters as plain functions and add interactivity from a separate file:

```python
# image_filters.py — your library, no interactive_pipe import
import numpy as np

def exposure(img, coeff=1., bias=0.):
    return coeff * img + bias

def black_and_white(img, bnw=False):
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img

def blend(img0, img1, blend_coeff=0.):
    return (1 - blend_coeff) * img0 + blend_coeff * img1
```

```python
# app.py — interactivity lives here
import numpy as np
from image_filters import exposure, black_and_white, blend
from interactive_pipe import interactive, interactive_pipeline, Control

interactive(
    coeff=Control(1., [0.5, 2.], name="exposure"),
    bias=Control(0., [-0.2, 0.2], name="offset expo"),
)(exposure)
interactive(bnw=Control(False, name="Black and White"))(black_and_white)
interactive(blend_coeff=Control(0., [0., 1.], name="blend coefficient"))(blend)

@interactive_pipeline(gui="qt")
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended = blend(exposed, bnw_image)
    return exposed, blended, bnw_image

sample_pipeline(np.array([0., 0.5, 0.8]) * np.ones((512, 256, 3)))
```

## Headless mode: same code, no GUI

The engine underneath the GUI is a `HeadlessPipeline` — use it for batch processing or tests:

```python
from interactive_pipe import pipeline  # alias of interactive_pipeline

@interactive_pipeline(gui=None)  # or gui="headless"
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended = blend(exposed, bnw_image)
    return exposed, blended, bnw_image

exposed, blended, bnw_image = sample_pipeline(input_image, bnw=True, blend_coeff=0.5)
sample_pipeline.export_tuning("my_tuning.yaml")  # save parameters...
sample_pipeline.load_tuning()                    # ...and reload them later
```

The exported YAML keeps one section per filter, so the parameters you tuned in the GUI feed your batch runs.

## Next steps

- [Backends](backends.md) — pick between Qt, matplotlib, Jupyter and Gradio.
- [Controls](../guide/controls.md) — all the widget declaration patterns.
- [Context, layout & events](../guide/context-layout.md) — share state between filters and control the display.
