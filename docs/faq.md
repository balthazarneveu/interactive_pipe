# FAQ

### What is the recommended way to access shared context?

Use the clean context API for direct access:

```python
from interactive_pipe import context, layout, audio, get_context

@interactive()
def my_filter(img):
    context["shared_key"] = "shared_value"  # Direct dict-like access
    context.brightness = 0.5
    layout.style("output_image", title="My Image")  # Layout helpers
    return img
```

### How do I change the layout?

*Can I change the grid layout of images live? (e.g. comparing 2 images side by side, then switching to a 2x2 grid for debugging)* — Yes, on the Qt backend. Use the `layout` proxy to control image arrangement and styling; see [Context, layout & events](guide/context-layout.md#layout-arrange-and-style-the-outputs).

### Do I have to remove `KeyboardControl` when using gradio or notebook backends?

No, don't worry — these map back to regular sliders.

### How do I play audio live?

🔊 Inside a processing block, write the audio file to disk and use the audio helper:

```python
from interactive_pipe import audio
audio.set(audio_file)
```

### Do I have to decorate my processing block using the `@interactive` decorator?

If you use the `@` decoration style, your function won't be usable in a regular manner (which may be problematic in a serious development environment):

```python
@interactive(angle=(0., [-360., 360.]))
def processing_block(angle=0.):
    ...
```

An alternative is to decorate the processing block from outside — in a file dedicated to interactivity, for instance:

```python
# core_filter.py
def processing_block(angle=0.):
    ...
```

```python
# graphical.py
from core_filter import processing_block
from interactive_pipe import interactive

interactive(angle=(0., [-360., 360.]))(processing_block)
```

### Can I call the pipeline in a command line/batch fashion?

Yes, headless mode is supported: `@interactive_pipeline(gui=None)` returns a `HeadlessPipeline` you can call like a plain function. See the [Quickstart](getting-started/quickstart.md#headless-mode-same-code-no-gui).

### Can I use in-place operations?

Better avoid these in general. To avoid making extra copies, computing hashes everywhere and losing precious computation time, there are no checks that inputs are not modified in place.

```python
# Don't do that!
def bad_processing_block(inp):
    inp += 1
```

### What happened to `global_params`?

The legacy names (`global_params`, `global_parameters`, `global_state`, `global_context`, `state`) were removed in 0.9.0. Declaring one of them as a filter keyword argument, or passing one as a pipeline-init argument, raises a `TypeError` with a migration hint. Use the clean context API instead: the `context` proxy inside filters, and `context={...}` at pipeline initialization. See the [migration guide](changelog.md).
