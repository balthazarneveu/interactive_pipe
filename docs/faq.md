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

*Can I change the grid layout of images live? (e.g. comparing 2 images side by side, then switching to a 2x2 grid for debugging)* — Yes, on the Qt and Dear PyGui backends. Use the `layout` proxy to control image arrangement and styling; see the [Layout guide](guide/layout.md).

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
@interactive(angle=(0.0, [-360.0, 360.0]))
def processing_block(angle=0.0): ...
```

An alternative is to decorate the processing block from outside — in a file dedicated to interactivity, for instance:

```python
# core_filter.py
def processing_block(angle=0.0): ...
```

```python
# graphical.py
from core_filter import processing_block
from interactive_pipe import interactive

interactive(angle=(0.0, [-360.0, 360.0]))(processing_block)
```

### Can I call the pipeline in a command line/batch fashion?

Yes, headless mode is supported: `@interactive_pipeline(gui=None)` returns a `HeadlessPipeline` you can call like a plain function. See the [Quickstart](getting-started/quickstart.md#headless-mode-same-code-no-gui).

### Can I use in-place operations?

Not on a filter's inputs, by default: filters receive their numpy inputs as read-only views, so `img += 1` raises right away (`FilterError: Filter 'bad' raised ValueError: output array is read-only`) instead of silently corrupting the buffers other filters or the cache share. Return a new array (`return img + 1`), or declare `@interactive(inplace=True)` on a filter that really mutates its inputs (it then receives private writable copies). `@interactive_pipeline(readonly_inputs=False)` restores the permissive behavior for a whole pipeline.

```python
# Raises with the default readonly_inputs=True
def bad_processing_block(inp):
    inp += 1
```

### What happened to `global_params`?

The legacy names (`global_params`, `global_parameters`, `global_state`, `global_context`, `state`) were removed in 0.9.0. Declaring one of them as a filter keyword argument, or passing one as a pipeline-init argument, raises a `TypeError` with a migration hint. Use the clean context API instead: the `context` proxy inside filters, and `context={...}` at pipeline initialization. See the [migration guide](changelog.md).

### My pipeline raises `PipelineSyntaxError`

The pipeline function is parsed, not executed, so its body may only chain filter calls: assignments, nested calls, literal keyword arguments and one `return`. The error names the file and line, quotes it and ends with a `Hint:` — usually "move this logic into a filter" (an `if`, arithmetic such as `img * 2`, a loop) or "pass it as a keyword argument" (`blur(img, 3)` → `blur(img, radius=3)`). A misspelled filter name gets a "did you mean" suggestion. See [what a pipeline body may contain](guide/decorators.md#what-a-pipeline-body-may-contain).

### `TypeError: pipeline 'p' got unexpected keyword argument(s)`

`pipe(img, gian=2.0)` (or `pipe.snapshot(..., gian=2.0)`) names a parameter no filter has. The message lists the available parameters and suggests the closest one (`'gian' -> 'gain'`); nothing has been run or changed. `print(pipe.summary())` lists every control with its range. A value outside a control's range is not an error: it is clamped, with a warning.

### Why is my slider called `amplify.gain`?

Two filters of the pipeline both have a `gain` control, so each widget is labelled after its filter (`amplify.gain`, `blend.gain`; a repeated filter's copy is `amplify_1.gain`). `pipe(img, gain=2.0)` still sets both; target one with `pipe(img, parameters={"amplify": {"gain": 2.0}})`, or `"amplify.gain"` in `snapshot` / `sweep`. Controls you name yourself (`name=...`) are never renamed. See [same parameter name in several filters](guide/controls.md#same-parameter-name-in-several-filters).

### Nothing shows up / no window opens

Run `interactive-pipe doctor` (or `python -m interactive_pipe doctor`): it lists the installed backends with the `pip install` command for each missing one, whether a display is available, and which backend `gui="auto"` picks. Over SSH, in CI or in a container there is no display: render PNGs instead with `pipe.snapshot(...)` or `interactive-pipe snapshot my_script.py` ([Snapshots](guide/snapshots.md)), or run headless with `gui=None`.

### How do I use interactive_pipe with a coding agent?

`interactive-pipe skill --install` installs a Claude Code skill (`~/.claude/skills/build-interactive-pipeline/`; `--project DIR` for one repository) that teaches the decorators, the pipeline-body rules and the describe → snapshot → read the PNG → sweep loop the agent uses to check its visual work. `interactive-pipe skill` prints it for other agents, and `interactive-pipe skill --agents-md` prints a short block for an `AGENTS.md` / `CLAUDE.md`. `interactive-pipe describe my_script.py --json` lists the controls of a script's pipelines.
