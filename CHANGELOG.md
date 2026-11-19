# Changelog

## Unreleased

- **Audio helpers, `interactive_pipe.sound`**: pure numpy (no new dependency) functions to use inside filters: `load` (WAV with the standard library, other formats through `ffmpeg` when installed), `resample`, `stft` / `istft`, `spectrogram` + `spectrogram_style` (a heatmap with time / kHz axes and a dB colour bar via `layout.style`), `add_noise` (white, pink, mains hum at a given SNR), `snr_db`, `denoise` (spectral gating, blind or from a noise sample), `time_stretch` and `pitch_shift` (phase vocoder). See [Audio](https://balthazarneveu.github.io/interactive_pipe/guide/audio/#audio-helpers-interactive_pipesound).
- **`demo/audio_processing_demo.py`**: switch between a synthesized singing voice and a music clip, corrupt with noise, denoise, pitch-shift and A/B listen (clean / noisy / processed) in the Qt or Gradio window.

## 0.10.0 (November 2026)

### New: video inputs and a timeline

- **`Video`**: give a pipeline input as `Video(source)` and the pipeline function, written for one frame, becomes a video tool. The window shows a timeline at the bottom; filters receive the frame under the playhead. The source can be a video file (OpenCV; `.gif` also with Pillow), a folder of images, a glob pattern or a list of paths, a numpy array `(T, H, W[, C])`, a torch tensor `(T, C, H, W)` / `(T, H, W[, C])` (`to_numpy=False` hands the tensor slices to the filters), or an iterator / generator / `cv2.VideoCapture` read up to `max_frames`. Files are decoded lazily. Options: `fps`, `start` / `stop` / `step`, `window=k` (the `k` frames ending at the current one, for temporal filters). ([guide](https://balthazarneveu.github.io/interactive_pipe/guide/video/))
- **The timeline is a control named `frame`** (`TimelineControl`): `pipe(Video(...), frame=20)` opens at frame 20, and `snapshot(..., frame=10)`, `sweep(..., frame=[0, 25, 50])` (a contact sheet), `describe()`, tuning files and sessions see it. Qt and Dear PyGui show a panel at the bottom of the window: transport buttons, timecode and a loop toggle above a film strip with a time ruler and playhead (scroll to zoom in, shift + scroll to pan); the other backends show a frame slider. Space plays / pauses, the left / right arrows step one frame. Playback runs at the video frame rate and skips frames when the pipeline is slower.
- **`Video(..., timeline=...)`**: `"shown"` (default), `"collapsible"` (a button folds the panel to its transport row), `"collapsed"` (folded at start) or `"hidden"` (keyboard only). The Qt panel follows the window's light or dark palette.
- **Custom formats and per-frame metadata**: `Video("raw/*.dng", loader=read_dng)` reads any file format (one file per frame; a folder or a list of paths too), and `FrameSource` subclasses or any lazy sequence (`len` + `[index]`, e.g. a torch `Dataset`) cover the rest. A loader, `FrameSource.read` or a sequence item may give `(frame, metadata)`, and `FrameSource.metadata(index)` adds more; filters read the metadata of the frame on screen as `context["timeline"].metadata`. `preview=` draws film strip thumbnails of frames that are not images as they are (raw mosaics, 10-bit data).
- **Read-ahead and background thumbnails**: the Qt and Dear PyGui windows decode the next `preload` frames (`Video(..., preload=8)`, `0` turns it off) in a background thread whenever the playhead moves, and a band on the ruler shows the frames in memory; `export_animation` reads ahead too. Film strip thumbnails are built in the background (grey tiles fill in, nearest the playhead first) and no longer evict frames from the cache. `Video(..., thumbnail_loader=)` (files) and `FrameSource.thumbnail(index)` give cheap thumbnails (the JPEG embedded in a DNG, a low-resolution level) so the strip never decodes full frames. Thumbnails now fill their tiles (no gap between them).
- **Several `Video` inputs share the timeline**, matched by time when their frame rates differ.
- **Filters read the position as `context["timeline"]`**: a `Timeline` with `frame`, `time`, `fps`, `n_frames`, `duration`, `progress` and `metadata`.
- **`export_animation` renders the video** of a pipeline with a `Video` input and no `TimeControl` (every frame, at the video frame rate); so does the *Export animation* action (<kbd>V</kbd>).
- Four demos: `video_grading_demo.py` (video file), `video_motion_demo.py` (numpy simulation, `window=3`), `video_compare_demo.py` (torch tensors, two frame rates), `video_raw_sequence_demo.py` (a custom RAW format with `loader=` and per-frame metadata).

## 0.9.5 (November 2026)

Common mistakes in pipelines used to build something that ran and was wrong. They now either do what was meant or fail with an error naming the line and the fix.

**Upgrading:** [Upgrading from 0.9](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/) shows every change below with the code before and after. `interactive-pipe check my_script.py` runs a script's pipelines once, without a window, and lists what now fails, with the file and line.

### Changes that can affect existing code

Pipeline function body (checked when the decorator runs):
- **Stricter pipeline body**: every top-level statement of a pipeline function is now validated. `if` / `for` / `while` / `with` / `try`, arithmetic and other non-call expressions (`b = a * 2`), `+=`, comprehensions, lambdas, statements after the `return`, `*args` / `**kwargs`, positional literals and builtins raise the new `PipelineSyntaxError` (a `ValueError`, exported from `interactive_pipe`) at build time, with the file, line, source line and a hint. Before, the body was flattened silently: branches always taken, loop bodies run once, arithmetic dropped (the pipeline returned `()`). Fix: move the logic into a filter ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#only-filter-calls-are-allowed)).
- **Variables and inputs are checked when the pipeline is built**: an undefined variable passed to a filter or returned (`offset(amplifed)`), a filter call missing a required input (`blend(img)` when `blend` takes two), and a method called on a pipeline variable (`img.copy()`) raise `PipelineSyntaxError` at the line, with a suggestion. Before, they failed inside the engine on the first run (`KeyError`, `missing a required argument`) or silently resolved a module-level name. Fix: the name the message suggests ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#names-are-checked-when-the-pipeline-is-built)).
- **Different exception types at build time**: an unknown filter name in a pipeline body used to raise `KeyError` and a non-callable `TypeError`; both now raise `PipelineSyntaxError` (a `ValueError`), with a suggestion. Fix: catch `PipelineSyntaxError` / `ValueError` ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#names-are-checked-when-the-pipeline-is-built)).
- **Keyword arguments in filter calls are now applied or rejected**: `amplify(img, gain=2.5)` used to be ignored silently; a literal value now sets that filter instance's parameter (and its control default, validated against the range). A keyword that is not a parameter of the filter, or a non-literal value (a variable), raises `PipelineSyntaxError`. Fix: a literal value, or check that the keyword was meant: it now takes effect ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#keyword-arguments-in-filter-calls-are-applied-or-rejected)).

Running a pipeline:
- **A filter must return what its pipeline line assigns**: a filter returning more values than the line assigns (`a = f(x)` with `return x, y`, or three values for `a, b = f(x)`) used to keep the first value(s) silently; it now raises a `FilterError` naming the pipeline line and the fix. A filter without any `return <value>` whose result is assigned raises likewise (an explicit `return None` is still accepted). `FilterCore` lists built by hand keep the old lenient behaviour. Fix: unpack every value, or `return (values,)` to keep a tuple / list as one value ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#a-filter-must-return-what-the-line-assigns)).
- **Unknown keywords when calling a pipeline raise**: `pipeline(img, gian=2.0)` raises `TypeError` listing the available parameters with a suggestion (headless and GUI), instead of being ignored. Fix: a name from the list ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#unknown-keyword-arguments-and-parameters-raise)).
- **`parameters={...}` is validated before being applied**: an unknown filter or parameter name raises `ValueError` with a suggestion and leaves the pipeline untouched. Before, an unknown parameter was stored, every later run failed inside the filter, and the pipeline stayed unusable. Fix: the suggested name ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#unknown-keyword-arguments-and-parameters-raise)).
- **Colliding control names are renamed**: two filters declaring an auto-named `gain` control in one pipeline used to raise `Duplicate control name`; they are now shown as `amplify.gain` / `blend.gain` (a repeated filter's copy as `amplify_1.gain`). Repeats of a single filter keep `gain`, `gain_1`; explicitly named (`name=...`) collisions still raise. `pipeline(img, gain=2.0)` sets every `gain`; use `parameters={"blend": {"gain": 2.0}}` (or `"blend.gain"`) to target one ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#two-filters-declaring-the-same-control-name)).
- **`HeadlessPipeline.save()` returns the list of written files** instead of the base path. Fix: keep the base path yourself ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#headlesspipelinesave-returns-the-written-files)).
- **`layout.grid` no longer changes what a pipeline call returns**: `pipe(img)`, `my_pipeline.headless(img)` and `save()` give the outputs in the pipeline function's `return` order and shape (a tuple; a list of rows only when the function returns a 2D list). Before, a filter calling `layout.grid([...])` turned the result into the grid's list of rows, in the grid's order, from that run on. The windows and snapshots still follow the grid. Fix: unpack in `return` order ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#layoutgrid-no-longer-changes-what-a-call-returns)).
- **A bare filter call drops its result**: `f(img)` on its own line, with `f` returning a value, raised `returned a single ndarray but the pipeline unpacks 0 values`; the filter now runs and the value is dropped, as in Python ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#a-bare-filter-call-drops-its-result)).
- **An unknown `on=` target only warns without a window**: a point / region control aimed at an output a `gui=None` pipeline does not produce logs a warning (it raised); GUI pipelines still raise at decoration and when a GUI is built ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#an-unknown-on-target-only-warns-without-a-window)).

Declaring controls:
- **`@interactive(gain=1.0)` raises** `ValueError` explaining that a range is needed (`gain=(1.0, [0.0, 2.0])`); a bare string likewise needs a list of choices. Before, no widget was created and nothing was said. Plain defaults in the function signature still mean "no widget" ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#a-bare-value-in-interactive-raises)).
- **Stricter control declarations**: `Control` rejects a step `<= 0` or larger than the range and `min > max` (`min == max` stays allowed); a range of more than `[min, max, step]` raises; a bool given to a numeric control raises `TypeError` (it was taken as 0/1) ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#stricter-control-declarations)).
- **`vmin`, `vmax`, `center` and `dpi` style values must be numbers** (`TypeError`) ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#stricter-control-declarations)).
- **`Literal` and `Enum` hints make dropdowns**: under `@interactive`, `Literal[...]` and `Enum` hints on a parameter with a default now make dropdowns (no such hint in the demos, samples or docs). Parameters without default stay inputs. Fix: drop the hint if no widget is wanted ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#literal-and-enum-hints-make-dropdowns)).
- **Re-decorating a function drops the controls that are no longer declared** (a notebook cell run again) ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#controls-belong-to-the-function)).
- **Controls are attached to the filter function itself** instead of a registry keyed by `module.qualname`: two scripts run in one interpreter with same-named `__main__` filters, or filters made by a factory, no longer share or replace each other's controls (`filter 'process_image' has no parameter 'hue_shift'`). Pipelines built from the same filter still share its control (documented in the controls guide, "One control per filter") ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#controls-belong-to-the-function)).

- **`graph_representation()` writes HTML by default** and returns the written `Path` instead of a `graphviz.Digraph`: a `path` without suffix gets `.html` (it was rendered to PDF by graphviz). Fix: `format="pdf"` (or a path ending in `.pdf` / `.svg` / `.png`) keeps the graphviz rendering and returns the `Digraph`, as before ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#graph_representation-writes-an-html-page)).

Display:
- **2D arrays are shown in gray on the matplotlib backend too** (it used matplotlib's default colormap, viridis, and kept the colour limits of the first frame, while Qt, Dear PyGui, Gradio and snapshots showed gray). Use `layout.style(name, colormap="viridis")` for a false-colour view ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#2d-arrays-are-gray-on-the-matplotlib-backend-too)).
- **Integer, RGBA and single-channel images are displayed the same everywhere**: `(H, W, 1)` as `(H, W)`, `(H, W, 4)` RGBA composited on a checkerboard, `bool` as 0 / 1, `uint8` / 255, `uint16` / 65535; other integer types are taken as values, like floats (so 0-255 data in `int64` is clipped, with a warning). Before, Qt raised on `(H, W, 1)` and RGBA, Dear PyGui on `(H, W, 1)`, and integer images were clipped (white) by the GUI backends. Fix: `astype(np.uint8)` or scale to `[0, 1]` ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#integer-rgba-and-single-channel-images)).
- **Arrays that cannot be displayed raise `DisplayError`**: channel-first `(3, H, W)` / `(1, H, W)` arrays, batches, empty, complex and object arrays raise one `DisplayError` (a `ValueError`) naming the output, the filter and the fix, in `snapshot` / `sweep`; a GUI window shows that message in the cell and keeps running. Before: a different crash per backend (`Expected 3-channel image, got 16 channels`, `Invalid shape (3, 12, 16) for image data`...) naming nothing ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#arrays-that-cannot-be-displayed-raise-displayerror)).
- **Figures made with `pyplot` are closed once displayed** (no leak while dragging a slider); `matplotlib.figure.Figure()` is the recommended way ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#pyplot-figures-are-closed-once-displayed)).
- **Figures made with `pyplot` are also closed after a headless run** (`pipe(x)`, `.headless`, `check`): a pyplot-written filter left one open figure per run, which a later `plt.show()` popped up. The returned figure stays usable (`savefig`); a direct call of the filter keeps it open ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#pyplot-figures-are-closed-once-displayed)).
- **`layout.style` calls on one output add up within a run**: a second call (`title=` set later) replaced the first one, dropping its colormap and range (`check` then warned "clipped to [0, 1]" with a fix already applied). A later call now changes only the keys it gives, `key=None` removes a key, the next run starts afresh ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#layoutstyle-calls-on-one-output-add-up)).
- **Figures laid out with `tight_layout()` are laid out again in their cell** (snapshots, sweeps, windows), their margins put back afterwards; a bare `subplots_adjust` is kept ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#figures-laid-out-with-tight_layout-are-laid-out-again-in-their-cell)).

Errors and logs:
- **A failing filter is reported once**: the engine no longer prints a `PIPELINE ERROR` banner before raising `FilterError` (headless calls, `snapshot`, `sweep`, tests and the `interactive-pipe` command showed the error twice). A script that does not catch it prints the banner once (full traceback with `INTERACTIVE_PIPE_DEBUG=1`); the Qt, Dear PyGui and matplotlib windows print it once on the console (not again on every slider move while it keeps failing) and show it in the window; Gradio shows it in the page (`gr.Error`) instead of a generic error, and keeps running ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#errors-and-logs)).
- **Out-of-range values log a warning**: a value outside a control's range (`pipeline(img, gain=99)`, tuning files, sessions) is still clamped, but now logs a warning naming the control, the value and the range ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#errors-and-logs)).
- **More reworded messages and one exception type** (for tests matching them): a wrong number of pipeline inputs says `pipeline 'p' expects 2 inputs (a, b), got 1` (was `Wrong amount of inputs`, `Cannot set inputs to None`, `... is not among ...`, `Single input provided ...`); a filter returning the wrong number of values says `filter 'f' returned 2 value(s) but the pipeline unpacks 3` (was `number of outputs` / `returning a single element`); a control value of the wrong type or not among the choices says `control 'gain' expects float, got str 'x'` / `'d' is not one of the choices [...]` (was `Expected ...` / `must be in ...`); a default of an unsupported type says `expected int, float, bool or str`; `PipelineCore(filters=[])` raises `ValueError` (a pipeline that calls no filter) instead of `IndexError`; slider values next to the Qt widgets read `0.5`, not `5.000e-01` ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#errors-and-logs)).
- **Reworded messages** (for tests matching message text): a default outside its range says so (`control 'gain': the default 5 is outside the range [0, 3]: choose a default between 0 and 3, or widen the range`, was `value_default 5 must be within value_range [0, 3]`); `snapshot()` / `sweep()` unknown-name errors read like the pipeline call's (`snapshot() got unexpected keyword argument(s) 'gian'. Available parameters: ... Did you mean 'gian' -> 'gain'?`); `layout.style(...)`, `context[...]`, `events[...]` and `audio.*` called outside a filter name the call and show the fix (the call moved into an `@interactive` filter); dropdown and range-slider value errors name the control; a wrong number of returned values gives the function name too when the pipeline calls the filter by another name (`filter 'split' (function 'two_values')`) ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#errors-and-logs)).
- **`import interactive_pipe` no longer imports matplotlib (`pyplot` included), pandas, OpenCV or Pillow**: they are imported when an image or curve is saved, loaded, plotted or rendered. Import them yourself if a script used them without importing them ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#errors-and-logs)).
- **A list returned by a filter is one value when the pipeline line assigns one name**: `dets = detect(img)` now receives the list whatever its length. Before, a 1-item list silently became its item and an empty list raised (2+ items raised too, asking for `return (dets,)`). Several names (`a, b = f(img)`) still unpack a list; tuples keep their rule (a 1-tuple is its item, a longer tuple assigned to one name raises naming the fix). ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#a-list-assigned-to-one-name-stays-a-list))
- **`snapshot` / `sweep` start from a fresh context** (see "Control semantics" below): a pipeline keeping state in `context` is rendered as on its first run, not continued from the live state. ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#snapshots-and-sweeps-start-from-a-fresh-context))
- **Each pipeline owns its controls**: two pipelines built from the same filter no longer share control values, and pipelines never connect nor change the declared `Control` object, so a direct call `f(img)` uses the declared default instead of the last value set in some pipeline. A pipeline starts from the declared control's value. ([upgrade](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/#each-pipeline-owns-its-controls))

### New features

#### See the result without a display: snapshots, sweeps, describe
- **Snapshots**: `pipeline.snapshot("out.png", img, gain=2.0)` renders what the GUI would show — the output layout, `layout.style` titles, images, curves, tables, text — to a PNG, headless (matplotlib object API, no `pyplot`, no window), with the parameter values as a caption. `path=None` returns an `(H, W, 3)` uint8 array; `output=` renders a subset. Parameter overrides apply to the call only: parameters, control values, layout, styles and last results are restored, also when a filter raises. Unknown parameter names raise `TypeError` with the available names and a close match.
- **Sweeps**: `pipeline.sweep("sweep.png", img, gain=[0.5, 1, 2])` renders a contact sheet over one parameter (a labelled row) or two (a grid with row and column labels); scalars are fixed overrides, `steps={"gain": 5}` spans a control's declared range, `output="all"` shows the whole layout per cell; by default each cell shows the first image the swept parameters change. `RangeControl` values are swept with a list of `(lo, hi)` pairs.
- **Describe**: `pipeline.describe()` returns a JSON-serialisable description (inputs, output layout, filters with routing, parameters and docstring line, controls with kind, value, range or choices, step, group, keys, tooltip); `pipeline.summary()` prints it as text.
- These are available on `HeadlessPipeline`, on `@interactive_pipeline(gui=...)` functions for any backend (without opening the window) and on `InteractivePipeGUI`.
- **Single filters (#21)**: every `@interactive` function gets `.snapshot()`, `.sweep()`, `.describe()`, `.summary()` and `.interact(img)` (open the GUI on this filter alone). The function itself is unchanged and its controls stay connected to the pipelines using it.
- **`INTERACTIVE_PIPE_SNAPSHOT=<path.png or folder/>`**: GUI-decorated pipelines render a snapshot there and return the results instead of opening a window (`{name}` is replaced by the pipeline name), so an unmodified GUI script can be checked headless.
- `snapshot()` / `sweep()` warn about outputs that cannot be displayed or are displayed misleadingly (dict, PIL, torch, integer images other than `uint8` / `uint16`, NaN/inf...) with the fix (`(C, H, W)` and 4D arrays now raise `DisplayError` instead); they no longer flag `(H, W, 1)`, RGBA (`(H, W, 1|4)`), `uint8` / `uint16` images, matplotlib figures or `Image` outputs, which now display correctly everywhere.
- New guide page: [Snapshots, sweeps and describe](https://balthazarneveu.github.io/interactive_pipe/guide/snapshots/).

#### Command line and coding agents
- **`interactive-pipe` command** (also `python -m interactive_pipe`), standard library only:
  - `interactive-pipe check SCRIPT.py [--json]`: the command to run after every edit. Builds every pipeline of an unmodified script without a window, runs each once (the called ones with the script's values, the only-defined ones taking no input with their defaults) and reports in one stable screen the pipelines, controls, outputs with type / shape / dtype / value range, every warning (misleading outputs, clamped values, anything logged) and the errors with the file and line of the user's code; exit code 1 on error.
  - `interactive-pipe snapshot SCRIPT.py [-o OUT] [--set NAME=VALUE] [--output NAME] [--pipeline NAME] [-- args]`: runs an unmodified GUI script as `__main__` and writes one PNG per pipeline call (`<pipeline>.png`, `<pipeline>_2.png` for a repeated call), stopping after `--max-calls` (10).
  - `--set t=4 --set mode=dark --set seed=0.2,0.4` sets parameters for the run: names go through the same resolver as `snapshot()` (the available names and a close match on a typo), values are converted to the type of the control (numbers, `true` / `false`, a choice, comma-separated numbers for ranges, points and regions); they win over the values the script passes. A wrong name or value exits with code 2.
  - `interactive-pipe sweep SCRIPT.py --param gain=0.5,1,2 [--param mode=dark,light] [--steps gain=5] [--output out|all] -o sweep.png`: a contact sheet per pipeline call of an unmodified script.
  - `interactive-pipe describe SCRIPT.py [--json]`: the controls and outputs of the pipelines a script runs, without a window.
  - When a filter raises, the commands print the error once, without interactive_pipe's own frames, and say which pipeline raised (`pipeline 'p' raised FilterError, see above`), exit code 1.
  - `interactive-pipe skill` prints the agent skill; `--install` copies it to `~/.claude/skills/build-interactive-pipeline/` (or `--project DIR`), refusing to overwrite a different file without `--force`; `--agents-md` prints a short block for a project's `AGENTS.md` / `CLAUDE.md`.
  - `interactive-pipe doctor [--json]`: versions, which GUI backends import (with the `pip install` extra for each missing one), whether a display is available, which backend `gui="auto"` picks.
- **The agent skill ships in the package** (`interactive_pipe.skill_path()`), rewritten against the current API: pipeline-body rules, controls, outputs, mouse input, proxies, the check / describe / snapshot / sweep loop, testing filters, headless use and an error table quoting the current messages (checked by a test). Its code blocks, the readme's and the quickstart's run in the test suite.
- `interactive_pipe.cli.set_snapshot_hook()`: lets a tool intercept the `INTERACTIVE_PIPE_SNAPSHOT` rendering of each pipeline call (used by the command).
- **Scientific gallery** (`demo/gallery/`, [docs](https://balthazarneveu.github.io/interactive_pipe/gallery/)): eight visual-debugging tools (camera ISP, frequency filtering, FIR / IIR filtering, detection overlay, optimiser traces, lens calibration, PID control, a stateful simulation) written from the skill alone; the skill now covers what they had to look up (curve / table / titled image constructors, returning a list, one slider for several filters, stateful simulations).
- **Scientific gallery, second round**: eight more examples (`g2_*.py`: stereo matching, segmentation, Kalman tracking, beamforming, DCT compression, heat diffusion, training curves, audio effects) on the gallery and examples pages; the skill now gives the data-object keywords, the audio signatures, the context re-run contract, styling merges and heatmap axes.

#### Declaring controls
- **Controls from annotations**: `gain: Annotated[float, (0.0, 3.0)] = 1.0`, `Annotated[int, (1, 15, 2), "label", "group"]`, `Annotated[bool, "Flip"]`, `Annotated[T, Control(...)]` (any control class), `Annotated[Tuple[float, float], (0, 1)]` (range slider), `Literal["a", "b"]` and `Enum` hints (the filter receives the member). Defaults come from the signature and are validated at decoration; `from __future__ import annotations` works. See [Controls from type annotations](https://balthazarneveu.github.io/interactive_pipe/guide/controls/#controls-from-type-annotations).
- `@interactive` works without parentheses.
- `@interactive(flip=True)` creates a checkbox (same as `(True,)`).
- `pipe(img, **{"amplify.gain": 2.0})` and control names are accepted by the pipeline call, like `snapshot` / `sweep`.

#### Pipeline functions
- Pipelines and their filters can be defined in an indented scope (inside `main()`, a test function): the source is dedented and names are resolved in the function's real scope (closure, then module globals).
- Dotted calls in the pipeline body (`np.abs(img)`, `lib.blur(img)`) resolve along the attribute chain; numpy ufuncs work as filters. Unknown names get a "did you mean" suggestion.
- Nested calls (`blur(amplify(img))`) and `return amplify(img)` are supported: the inner call becomes its own node, named after its source (`amplify(img)`), which is also its display title.
- Literal keyword arguments in filter calls (`amplify(img, gain=2.5)`) set that instance's value and its control default (see the behaviour change above).

#### Scientific outputs: figures, heatmaps, overlays
- **matplotlib figures as outputs**: a filter may return a `Figure` (or an `Axes`). It is rasterised with Agg in one shared place (120 dpi, `layout.style(name, dpi=...)`), so it shows the same on every backend, in `snapshot` / `sweep` and in `export_animation`; `save()` writes it with `savefig` (`.png`, `.pdf`, `.svg`).
- **Heatmaps**: `layout.style(..., colormap="viridis", vmin=0, vmax=1)` displays 2D arrays as heatmaps on every backend (vmin/vmax default to the data range). Unknown colormaps raise with a suggestion, unknown style keys warn once listing the supported ones, and `subtitle=` is shown after the title.
- **Heatmap colorbar**: `layout.style(name, colormap=..., colorbar=True, unit="dB")` draws the scale into the displayed image (identical everywhere, legible on small maps); `center=0` makes the range symmetric for diverging colormaps. NaN and masked values are shown in magenta and ignored by the automatic range.
- **`interactive_pipe.draw`**: `points`, `boxes`, `lines`, `polygon`, `text`, `mask` — pure numpy + Pillow functions that draw detections, keypoints, regions and labels on float or `uint8` images, keeping their dtype and range.
- **`Image` outputs**: a filter may return an `interactive_pipe.Image`; its array is shown and its `title` is the cell title unless `layout.style` sets one.
- The Qt pixel readout reports the original scalar of a heatmap, in data coordinates, also when it is shown enlarged with a colorbar.
- New demos: `demo/matplotlib_figure_demo.py`, `demo/overlay_demo.py`. New guide page: [Figures, heatmaps and overlays](https://balthazarneveu.github.io/interactive_pipe/guide/figures-and-overlays/).
- **Heatmap axes**: `layout.style(name, extent=(x_left, x_right, y_bottom, y_top), xlabel=..., ylabel=...)` draws a frame, round ticks and labels around a heatmap, into the image like the colorbar (every backend, snapshots); the Qt readout shows the extent coordinates and point / region controls map through the margins (`display.HeatmapGeometry`).
- **`Curve(xscale=..., yscale=...)`**: `"linear"`, `"log"` or `"symlog"` axes, on every backend (Dear PyGui's native axis scale) and in snapshots.
- **`audio.set(signal, sample_rate)`** plays a numpy signal (mono or stereo, float in [-1, 1] or int16) through a temporary WAV the library writes and removes; `audio.set(path)` is unchanged; wrong calls raise `TypeError` showing both forms; headless runs touch no file and no audio device.
- **`HeadlessPipeline.styles`** (also `my_pipeline.headless.styles`): the `layout.style` options of each output after the last run, so readout titles can be tested.
- `interactive_pipe.DisplayError` is exported.

#### Mouse input: points and regions
- **`PointControl((x, y), on="img")` and `RegionControl((x0, y0, x1, y1), on="img")`**: a click sets the point, a shift-drag draws the region, on the output named by `on=` (default: the first image). Values are fractions of the image size in [0, 1]; `to_pixels(value, img)` gives the pixel `(col, row)` or the slice bounds `img[y0:y1, x0:x1]`. Validated (length, numbers, range; a region is reordered); an unknown `on=` name fails when the GUI is built, with the available outputs.
- Qt, Dear PyGui and matplotlib: click (moving less than 3 screen pixels) and shift-drag, through zoom / pan and back to data pixels for heatmaps with a colorbar; left-drag keeps panning. Gradio: a click sets the point. The window draws the marker and the rectangle over the image, the outputs are untouched.
- Where gestures are not available (notebook, Gradio regions, any backend that does not implement them) the controls are shown as sliders in [0, 1] (`seed x`, `seed y`, ...).
- Headless they are ordinary parameters: `pipe(img, seed=(0.2, 0.4))`, `snapshot`, `sweep(seed=[...])`, tuning files, `describe()` (kinds `"point"` / `"region"` with the target output), `interactive-pipe snapshot --set seed=0.2,0.4`.
- New demo: `demo/pointer_demo.py`. New guide page: [Mouse input](https://balthazarneveu.github.io/interactive_pipe/guide/mouse-input/).

#### Pipeline diagram without graphviz
- **`graph_representation()` writes a standalone HTML page** (inline SVG, CSS and a few lines of JS, no dependency, no external URL, light and dark themes): inputs at the top, filters with their parameters (value and range / choices of their control, fixed values dimmed), outputs at the bottom, each buffer labelled under the filter producing it; hovering a node highlights its connections. The layered layout is computed in pure Python (`interactive_pipe.headless.graph_html`). Default path `<pipeline name>.html`, returns the written `Path`; `view=True` opens it in the web browser (never under `INTERACTIVE_PIPE_SNAPSHOT`).
- The ++g++ key writes `<pipeline name>_graph.html` and opens it in the browser, instead of failing with Graphviz install instructions when graphviz is missing.

#### Saving and tuning
- `HeadlessPipeline.save()` writes the outputs according to their type: numpy images through `Image`, 1D arrays as `.csv`, other arrays as `.npy`, `Image` / `Curve` / `Table` with their own `save`, strings as `.txt`; other types are skipped with one warning. The GUI save action (`w`) uses the same dispatch.
- `HeadlessPipeline.load_tuning(path)`, the name the docs already used (alias of `import_tuning`).

### Improvements & bug fixes

Errors that now explain themselves:
- A lambda or a function without source code (built with `exec`) used as a pipeline gets an explanation (`PipelineSyntaxError`) instead of `Function AST node is malformed` / `OSError`.
- Calling a pipeline with the wrong number of inputs says `pipeline 'p' expects 1 input (img), got 0` (and names the missing keys for `inputs={...}`), instead of `Cannot set inputs to None when inputs_routing is defined`.
- `context["key"]` read before any filter wrote it: the error lists the keys present and explains that filters run in body order.
- Control declaration errors name the filter and the parameter and report the real problem (not "max parameter should be numerical too" / "wrong abbreviation").
- A positional value for a controlled parameter in a direct call wins (`amplify(img, 2.0)` raised "multiple values"); unknown keywords name the filter with a suggestion.
- numpy scalars (`np.float32(2.0)`) are accepted as control values; type errors name the control.

Filters and pipelines:
- A `functools.partial` (or any callable object) can be used as a filter; it used to fail with `AttributeError: __qualname__`.
- A plain `FilterCore` instance used in a pipeline function no longer fails with `AttributeError: controls`.
- The GUI `__call__` accepts `inputs={...}` like the headless one.
- `HeadlessPipeline.save()` used to log one traceback per numpy output and write nothing but curves; it also saved nothing for 2D output layouts.

Display:
- `layout.style` heatmap options now apply in snapshots and sweeps (they were GUI-only) and on every Gradio refresh (they only applied to the first frame); `export_animation` exports outputs as the GUI shows them (styled heatmaps in colour).
- A `layout.style` call without `title=` no longer blanks the cell title in the GUI windows: the output name is shown.
- The sweep caption keeps another filter's parameter with the swept parameter's name.
- **Figures in sweeps** are drawn at the pixel size of their cell (their text shrank with the number of panels: positions were taken relative to the panel), at least as wide as a `Curve` cell, without a frame; a sweep panel of four or more outputs in one row or column is folded into a near-square grid.
- Snapshot and sweep captions name a control shared by several filters by its own name (`process noise q=1`), once, instead of under its first filter's parameter.
- A colorbar's end label and its nearest round tick keep a clear gap (`4.2` and `4.0` nearly touched on tall maps); a heatmap `xlabel` with descenders is not clipped.
- `cache="graph"`: a filter reading back a context key it wrote in the same call is no longer its own feedback reader (it ran once more after every change). Tested: a filter reading a key written by an earlier filter re-runs whenever that filter does, in every cache mode.
- The "clipped to [0, 1]" warning no longer suggests a heatmap style that is already set (it says the style applies to 2D arrays only).
- `import interactive_pipe` is ~4x faster (about 1.0 s -> 0.22 s here, `interactive-pipe --help` 1.05 s -> 0.3 s); `Curve.save` to an image file uses matplotlib's object API instead of `pyplot`.
- Qt: a window dropped while still on screen (several GUIs in one process, notebooks) no longer crashes the process with a segmentation fault when the garbage collector deletes it during one of its own paint events (it is now deleted by Qt's event loop), and a `threaded=True` GUI collected without `close()` / `run()` no longer aborts it (`QThread: Destroyed while thread is still running`); a Dear PyGui GUI called a second time (a decorated `gui="dpg"` pipeline) no longer segfaults.

Demos and docs:
- Every script of `demo/` and `samples/` now runs headless in the test suite and must render a non-blank snapshot. Fixed on the way: the blur / sharpen of the panel and grouped-controls demos took ~5 s per slider move (per-pixel Python loop, now vectorized), and `panel_position_demo.py`'s default crop showed a blank corner of the image (the crop is now in percent).
- FAQ: in-place operations on inputs raise by default (read-only inputs) — the answer said there were no checks; new entries for `PipelineSyntaxError`, unknown keyword arguments, renamed controls, "no window" and coding agents.
- New page: [Upgrading from 0.9](https://balthazarneveu.github.io/interactive_pipe/upgrade-from-0.9/); the examples page lists every demo and the scientific gallery; the readme has a short feature list.

### Control semantics: shared controls, per-pipeline state
- **One control for several filters**: pass the same `Control` object to several `@interactive` decorators (`band = RangeControl(...)`; `@interactive(band=band)` on two filters, the parameter names may differ): one widget, one value, set in all of them, on every backend, in `pipe(img, band=...)`, `snapshot`, `sweep` (one axis, caption once), tuning files and `describe()` (new `targets` list per control). An annotation alias whose control has a `name=` is shared the same way; an unnamed alias stays one control per filter. Two different controls with the same explicit name still raise, the message says how to share.
- GUI panels list the controls of their own pipeline only (`Panel.controls_among`).
- **Log-scale sliders**: `Control(1e-2, [1e-4, 1e-1], scale="log")`, `(1e-2, [1e-4, 1e-1, "log"])` or `Annotated[float, (1e-4, 1e-1, "log")]`; the slider moves evenly over decades on every backend (Qt, Dear PyGui, matplotlib, notebook `FloatLogSlider`, Gradio), the label, sweeps (`steps=` geometric), `describe()` (`scale`) and tuning files hold the real value.
- A point / region control whose `on=` names no output of the pipeline fails when the pipeline is built (before: when a GUI, `describe()` or a snapshot was made). `export_animation` display errors name the output and its filter.
- **Nicer default float step**: 1, 2 or 5 × 10^k closest to 1/100 of the range (was exactly range/100, e.g. 0.0195); slider values are snapped without float noise.
- **Decorated filters are testable as plain functions**: called directly (outside a pipeline run, e.g. `compare(out, gt)` in a unit test), `layout.style` / `layout.grid` / `audio` calls are validated then do nothing, `events.get` returns its default and `context` is a scratch dict for that call (reading a key nobody wrote raises a `KeyError` saying the filter is called directly). Before, they raised `RuntimeError`. Outside any filter these calls still raise, with a message naming both ways to call a filter.
- **`my_pipeline.headless(img, gain=2.0)`** returns the outputs of a GUI-decorated pipeline (any `gui=`) as a tuple, like a `gui=None` pipeline, without opening a window; it is a `HeadlessPipeline` of the same function with its own control values (on a `HeadlessPipeline`, `.headless` is itself). `my_pipeline.run(...)` and other guesses raise, pointing to it. `HeadlessPipeline.__call__` has a docstring.
- **Snapshots and sweeps of stateful pipelines are reproducible**: each `snapshot` call and each `sweep` cell starts like a first run (the `context` holds only what was given from outside, at construction or with `context=`; key-bound events off; no cached result), and the live pipeline's context, events and cache are put back afterwards. Before, a filter accumulating state in `context` made every picture depend on the runs before it. `snapshot(..., runs=N)` / `sweep(..., runs=N)` show the N-th run from that fresh start (warm-up).

### Display polish
- **"Nothing found" no longer crashes**: every `draw` function accepts zero marks with any `color` (including `color=[]`) and returns the image unchanged; an empty `Table` shows its header row and "(no rows)" on Qt, Dear PyGui, matplotlib, Gradio and in snapshots (it raised in matplotlib). `Table` accepts numpy arrays, tuples and pandas `Series` as dict columns (numpy scalars become `int` / `float`). Qt and matplotlib windows draw tables like snapshots (natural row height, kept on resize; the title is no longer cut); Gradio shows the column names as headers instead of a first data row.
- **Colorbar labels**: `unit` is written once above the bar instead of after every tick; `colorbar="some text"` writes a longer label along the bar; all labels of a bar have the same number of decimals; both ends are always labelled (within 0.5 % of the true value) and a round tick that would overlap one is dropped; very large / small ranges show one `×10ⁿ` multiplier instead of `1e-03` on each tick.
- **matplotlib figure outputs are drawn at the size of their cell** (keeping their aspect ratio) in snapshots, sweeps, the Qt window (again after a resize), the matplotlib and notebook windows and Dear PyGui (the size of a plot cell): their text is the size of a `Curve`'s next to them whatever the `figsize`, and a shrunk figure with default margins is laid out tight so its axis labels are not cut. Gradio and `export_animation` keep the `figsize` at 120 dpi. Snapshot curves use matplotlib's default tick size (was 8 pt), like the GUI.
- **Readouts**: a title set per frame (`layout.style("out", title=f"PSNR {psnr:.2f} dB")`) now also updates the Gradio component label (it kept the first one); it already followed each frame elsewhere and in each sweep cell. `str` outputs are written at 12 pt and wrapped to their cell on every backend (the matplotlib and notebook windows did not wrap; display errors are no longer pre-wrapped at 36 characters).
- **Slider values are written like a person would**: `6`, `0.1`, `0.005`, `20000`, and `1e-05` only below 1e-4 / from 1e6 (Qt showed `6.000e+00`), the same on Qt, Dear PyGui, matplotlib, Gradio's range slider and in snapshot captions (`interactive_pipe.graphical.value_format`); the notebook uses ipywidgets' closest format (6 significant digits).
- Errors raised while building a Gradio or notebook control widget name the control and its filter (`control 'gain' (filter 'amplify'): Expected int control type, ...`).

### Show reel: -b on the command line, colormaps, Qt plot cells
- **`-b` / `--backend` on every script**: a pipeline that keeps the default `gui="auto"` picks its backend from the command line with no code, `python my_script.py -b mpl` (also `--backend dpg`, `--backend=qt`, alias `--gui`; `-b headless` runs once without a window). The decorator only peeks at `sys.argv` (`interactive_pipe.cli.gui_from_argv`), values that are not backend names are ignored, and an explicit `gui=` is never overridden. Precedence: `parse_gui_args` values > explicit decorator arguments > `-b` > `INTERACTIVE_PIPE_GUI`. `parse_gui_args` / `add_gui_arguments` accept `-b` and `--backend` as aliases of `--gui`.
- Qt: plot and table cells keep a legible minimum size (360x270) and a constrained layout. They used to shrink to the height of the smallest image of their row, with the title and axis labels cut off, and a window holding only plots opened about 190 px high.
- Qt: a window holding only plots or tables grows to give its controls room (the automatic sizing was only triggered by image cells, leaving about 60 px for the sliders).

### Improvements & bug fixes
- Calling a headless pipeline that takes no inputs again (`pipe()`, `pipe(gain=2.0)`) no longer resets its cache: only the filters affected by the parameter change are recomputed, and `last_run_report.cached` reports the others. Passing inputs still invalidates everything, as before.
- A pipeline without inputs can be run before its first call (`pipe.run()`, `export_animation(pipe, ...)`) instead of raising "Cannot access uninitialized inputs!".
- **Zooming a heatmap with a colorbar** ([#79](https://github.com/balthazarneveu/interactive_pipe/issues/79)): the map and its colorbar were zoomed as one image, so the cell framed another place than its neighbours (often the colorbar itself). On Qt and Dear PyGui the colorbar now stays fixed on the right of the cell and keeps its size; only the map zooms and pans, and the shared view center is taken on the data area, so cells whose data have the same size show the same pixels. At zoom 1 nothing changes.
- **Dragging a region no longer makes the window flicker** ([#79](https://github.com/balthazarneveu/interactive_pipe/issues/79)): an output depending on the region (a crop) changed size at every mouse move, the grid was laid out again and moved the image under the mouse, which changed the region again (worst at 1:1). On Qt and Dear PyGui the grid keeps its layout during a point / region gesture and takes the new sizes once the mouse is released.
- The pre-0.9 control tuple with keyboard keys, `(100, [0, 200], "X", ["left", "right"])`, now says the form was removed and shows `KeyboardControl(default, [min, max], name=..., keydown=..., keyup=...)` instead of only "group shall be a string or Panel".

## 0.9.4 (November 2026)

### New features
- Qt: the controls below the images spread over several columns (in order, balanced heights) when they would not fit the height left by the images; the window grows wider for them, up to the screen width. They scroll only when even that is not enough. The columns follow the window size.
- Dear PyGui: the controls below the images spread over several columns the same way (columns at least 420 px wide, within the current window width).
- Qt: 1:1 (key `1`) grows the window, up to the screen size, so the images show whole at their native size; the controls below get the room left and scroll in their own area (the window outgrows the screen only when the images alone do not fit). Fit (key `0`) restores the previous size. The controls also scroll when the window is too small for them in the fit view, and the window no longer extends under the panels on Wayland, where Qt reports them as available screen.
- Qt and Dear PyGui: zooming out stops at the fit size (or at the native size, when an image is smaller than its cell at 1:1), and an image stays centered along each axis where it fits its cell, so it can no longer be shrunk to a small off-center thumbnail. Zoomed in, panning (and zooming near a corner) stops at the image edges instead of showing empty room past them.
- Dear PyGui: image cells get the Qt image viewer controls. Mouse wheel zooms around the cursor, left-drag pans, double-click fits back, and the View menu / keys 0 (fit), 1 (1:1), + and - (main and keypad) work as on Qt. 1:1 shows the whole images at their native size: the cells are resized, the sliders move to make room for them and the window grows to fit (as far as the screen allows; beyond it the images still show whole and the sliders scroll in their own area, the window itself never scrolls). Fit restores the previous window size. Zoom and pan are synced across cells; reset (`r`) also fits the view back. No pixel-value readout yet.

## 0.9.3 (November 2026)

### Packaging
- The PyPI package now ships only the Qt backend on top of the core (numpy, matplotlib, Pillow, PyYAML, PyQt6) instead of every backend. Dear PyGui, Jupyter, gradio, OpenCV, pandas and pytest are opt-in: `pip install "interactive-pipe[dpg]"`, `[notebook]`, `[gradio]`, `[opencv]`, `[pandas]`, or `[full]` for everything. New `gradio`, `opencv` and `pandas` extras.

## 0.9.2 (November 2026)

### New features
- **`RangeControl((lo, hi), [min, max])`**, a two-handle min/max control (#60): the filter receives a sorted `(lo, hi)` tuple clamped into the range and tuning files store it as a list. One real two-handle slider on every backend: native on matplotlib and notebook, a custom single-track widget on Qt, Dear PyGui (drawn, resizes with its cell) and gradio (`gr.HTML`). A control declared in `@interactive` now takes precedence over a tuple default in the function signature instead of raising "already attributed".
- **Session restore**: `@interactive_pipeline(..., restore_session=True)` saves the slider values when the GUI exits and restores them at the next launch (`~/.interactive_pipe/sessions/<name>.yaml`, or `session_path=`). Corrupt files and stale entries are ignored; the `k` key / Pipeline → Clear saved session deletes the file and resets the sliders. `save_session()`, `load_session()`, `clear_session()` and `session_file` are public.
- **Animation export**: `export_animation(pipeline, path, duration=5.0, fps=10.0, time_control=None, output=None, loop=0)` renders a `TimeControl`-driven pipeline to an animated GIF (Pillow) or to numbered PNG frames, headless. In the GUI, press `v` or use Pipeline → Export animation. `output` picks an index or a `(row, col)` cell; the time control value is restored afterwards.
- **Command-line and environment backend selection** (#33): `interactive_pipe.cli.parse_gui_args()` / `add_gui_arguments()` / `gui_kwargs_from_args()` add `--gui {auto,qt,dpg,mpl,nb,gradio,headless}`, `--fullscreen`, `--maximized`, `--size WxH` and `--name` to any argparse parser and return the matching `interactive_pipeline(**kwargs)`. The `INTERACTIVE_PIPE_GUI` (auto/qt/dpg/mpl/nb/gradio/headless/none) and `INTERACTIVE_PIPE_SIZE` (fullscreen/maximized/WxH) environment variables override `gui="auto"` and an unset `size`. Precedence: CLI values > explicit decorator arguments > environment.
- **Dear PyGui backend (`gui="dpg"`)**: a GPU-rendered window built on [Dear PyGui](https://github.com/hoffstadt/DearPyGui) (`pip install "interactive-pipe[dpg]"`). Same declarative feature set as Qt — sliders, checkboxes, dropdowns, text prompts, rangeless numeric inputs, image buttons, knobs for `CircularControl`, panels at any position (nested, collapsible, detached), keyboard shortcuts and `KeyboardControl`, `TimeControl` animations, live layout changes — with images uploaded as raw float textures, native zoomable plots for `Curve` outputs and native tables. The `auto` backend picks it after Qt and before matplotlib. No audio playback.
- **Menu bar** (Qt and Dear PyGui): File / View / Pipeline / Help menus expose every GUI action (save images, export/import tuning, quit, fullscreen, reset, print parameters, graph, help) with its shortcut shown next to the entry. Keys, menu entries and the F1 help come from a single actions registry (`interactive_pipe.graphical.actions`).
- Qt backend: image cells are now a zoomable viewer. Images fit their cell by default, keep their aspect ratio and rescale with the window, so large outputs no longer blow the window up. Mouse wheel zooms around the cursor, left-drag pans, double-click resets to fit, and a 1:1 mode is available (View menu / keys 0, 1, +, -). Zoom and pan are synced across all cells so before/after comparisons stay aligned. Hovering shows the pixel coordinates and the raw float value in the status line. Saving (`w`) still writes full-resolution results.
- **Status line and profiling** (Qt and Dear PyGui): a status line at the bottom of the window shows the last run (`run 12.3 ms · 3 filters · 1 cached`) or the filter that failed; on Qt it also shows the hovered pixel value. Press `t` (Pipeline → Profile last run) for a per-filter timings table; headless pipelines expose the same data as `pipeline.last_run_report` (a `RunReport`: per-filter seconds, cached filters, total, failing filter).
- **Coalesced refresh** (Qt and Dear PyGui): moving a slider no longer runs the pipeline inside every widget event. Updates are merged and run once per event-loop pass (Qt) or once per frame (Dear PyGui) with the latest values, so dragging a slider over a slow pipeline stays fluid instead of queuing one run per tick.
- **Threaded runs on Qt (opt-in)**: `@interactive_pipeline(gui="qt", threaded=True)` runs the pipeline in a worker thread. Widgets stay live during slow runs, the status line shows `running…`, and requests made during a run collapse into one follow-up run with the latest values. Key events and resets still run synchronously (serialized with the worker).
- **Errors shown in the window** (Qt, Dear PyGui, matplotlib): a filter raising during a refresh no longer escapes the GUI callback leaving a stale frame. The failing filter's cell shows `⚠ <filter> raised <ExcType>: <message>` in red, the other cells are kept, the status line reports the error, `window.last_error` holds the `FilterError`, and the next successful run restores the display. The compact error report is still printed to the terminal.

### Improvements & bug fixes
- Qt `threaded=True`: saving images waits for the run in progress and uses the current parameters; a slider change made during a run is no longer reverted; errors raised outside filters are shown instead of leaving the status on "running…"; reset and import run the pipeline once in the worker without freezing the window; results are displayed with the titles and layout of their own run; `audio=True` is refused with a `ValueError`.
- Qt: switching a cell between image and curve/table no longer leaks views in the zoom sync (zoom +/- uses the right view), and the window still grows to fit the images when the very first run failed.
- A filter that raised kept its previous output in cache, so changing only a downstream parameter showed that stale output as valid; the failing filter is now recomputed on the next run (`cache=True` and `cache="graph"`).
- `bind_key_to_context` on a default shortcut key (e.g. `1`, `t`) also ran the built-in action; user context events now replace the default shortcut on that key (`bind_key` bindings are unchanged).
- Dear PyGui: keyboard shortcuts no longer fire while typing a file name in the file dialog or while the message window is open.
- The timings table (`t`) marks the failing filter of an aborted run and labels the total as measured until the error.
- The `e` key (export tuning) silently did nothing (`export_tuning()` was called without a path); it now asks for a path and writes the yaml/json file.
- `w` / `e` / `o` no longer freeze the GUI waiting for a path typed in the terminal: Qt and Dear PyGui open a native file dialog (cancel does nothing). Backends override `InteractivePipeGUI.ask_path`; matplotlib keeps the terminal prompt (empty input cancels).
- A filter that changes its output type between frames (image one frame, text/curve/table the next) now rebuilds the display cell on Qt and matplotlib instead of feeding the new content to the previous widget; 1D signals update correctly on matplotlib.
- Pipeline inputs are no longer deep-copied on every run when the read-only input views already protect them (`safe_input_buffer_deepcopy=None`, the new default, copies only unprotected objects; pass `True` to force the previous behavior).
- A key-bound event (`bind_key_to_context`) only re-runs the filters that read it through `events` (and what depends on them) instead of resetting the whole cache.
- `Image.save_image` / `load_image` accept RGBA arrays with both backends; Qt icon buttons highlight the current choice and follow resets; `interact(gui="headless")` gives a clear error.
- Internal: window classes expose the requested size as `window_size` (Qt's `QWidget.size()` is no longer shadowed), `InteractivePipeGUI.help` is now `show_help` (alias kept), the Qt widget module reuses the binding cascade of `qt_backend`.
- Numeric controls declared without a `value_range` (`Control(3)`, `Control(0.5)`) crashed every GUI backend; they now render as spin boxes (Qt), a numeric text entry (matplotlib), `gr.Number` (gradio) and `IntText`/`FloatText` (notebook).
- 2D layouts keep `None` placeholders so cells and titles stay aligned, and jagged grids (rows of different lengths) no longer crash when the layout changes.
- `cache=True` no longer raises "truth value of an array is ambiguous" when a filter has an array-valued keyword default (e.g. a numpy kernel).
- `SingleCurve.save("plot.png" / ".jpg")` works (it raised `KeyError`), and curve plots update correctly when the number of curves or the signal length changes between frames.
- `FilterError` tracebacks show user code only, also for installs from PyPI (framework frames were only filtered in editable checkouts).
- Gradio: controls without a widget (single-choice dropdowns) no longer shift the event bindings of the following widgets; curve outputs no longer leak one matplotlib figure per refresh.
- Qt: loading a tuning file (`o` key) no longer fails when the file omits a control or when two filters share a parameter name; the Qt6 audio volume is set on the correct scale; widgets hand the window values in the control's own domain (no more monkeypatching of `Control` objects).
- `PipelineCore.parameters` returns copies, so mutating the returned dicts no longer silently alters filter state.
- Per-frame diagnostics (engine timings, control updates, grid sizes) moved from INFO to DEBUG; output buffers are no longer deep-copied on every GUI refresh.
- Dear PyGui: `close()` / full-screen toggle after `run()` no longer segfault, a filter error during the render loop still releases the context, plot zoom & pan survive refreshes (axes refit only when the data extent changes), curves with `y=None` no longer leave stale series, scaled tables keep their size, and unreadable icons raise `FileNotFoundError`; the 1D-signal "audio not supported" warning (dpg and Qt) is logged once instead of every frame.

## 0.9.1 (July 2026)

### New features
- **Dependency-aware cache (`cache="graph"`)**: a new opt-in cache mode that recomputes a filter only when it is actually affected by a change — its own sliders moved, one of its producers in the data-flow graph was recomputed, or a `context` key it reads was updated (tracked at runtime). Unlike `cache=True` (a sequential prefix cache that recomputes every filter after the change in source order), independent branches are left untouched. `cache=True` / `cache=False` behavior is unchanged.
  - `cache="graph-strict"` behaves like `"graph"` but hands out `context` numpy arrays as read-only views, so accidental in-place mutation of shared context data raises at the offending line (debugging helper).

### Improvements & bug fixes
- **Read-only filter inputs by default (`readonly_inputs=True`)**: filters now receive their numpy inputs as read-only views, so an in-place mutation (`img += 1`) raises immediately instead of silently corrupting sibling filters or cached buffers. Declare `@interactive(inplace=True)` on a filter that intentionally mutates its inputs — it then receives private writable copies. Pass `readonly_inputs=False` to `@interactive_pipeline(...)` to restore the previous permissive behavior.
- In-place mutation of torch tensor inputs is now detected as well (torch tensors do not support numpy's read-only flag), surfacing the same class of silent-corruption bug for PyTorch-based filters.

## 0.9.0 (July 2026)

### Breaking changes
- Removed implicit dict injection: declaring `global_params` / `global_parameters` / `global_state` / `global_context` / `context` / `state` as a filter keyword argument now raises `TypeError` at filter construction. Use the `context`, `layout` and `audio` proxies instead (see migration guide below).
- Removed pipeline-init aliases (`global_params=`, `state=`, ...): pass `context={...}`.
- Removed `SharedContext` / `SharedContext.injected()`.
- Removed layout aliases `layout.set_style` / `set_grid` / `canvas` / `set_canvas` (use `layout.style` / `layout.grid`) and the write-only `Control.group` attribute (use `Control.panel`).
- Requires Python >= 3.9.

### Improvements & bug fixes
- `import interactive_pipe` no longer fails when neither OpenCV nor Pillow is installed (the error is raised on first image save/load) and no longer overrides `sys.excepthook` as an import side effect.
- Fixed the wavio availability flag, an unbound variable in audio saving, the dropped step default for string controls, and the filter-signature cache that never cached.
- Runtime validation uses proper `TypeError`/`ValueError` exceptions instead of asserts; library diagnostics go through `logging` instead of `print`.

### Migration from old `context={}` or `global_params={}` patterns

```python
# OLD (removed in 0.9.0 - now raises TypeError at filter construction)
from interactive_pipe import interactive


@interactive(brightness=(0.5, [0.0, 1.0]))
def apply_brightness(img: np.ndarray, brightness: float = 0.5, global_params={}):
    global_params["brightness"] = brightness  # Storing shared data
    global_params["__output_styles"]["output"] = {"title": "Brightened"}  # Setting layout
    return img * brightness


# NEW (recommended) - using context and layout proxies
from interactive_pipe import interactive, context, layout


@interactive(brightness=(0.5, [0.0, 1.0]))
def apply_brightness(img: np.ndarray, brightness: float = 0.5):
    context["brightness"] = brightness  # or: context.brightness = brightness
    layout.style("output", title="Brightened")
    return img * brightness
```

The new API provides:
- `context` - For sharing data between filters (replaces `global_params["key"]`)
- `layout` - For controlling output display (replaces `global_params["__output_styles"]`)
- `audio` - For audio playback control
- `get_context()` - Get the shared context dictionary directly

## 0.8.10 (March 2026)
- Bugfix for jupyter notebooks backends.

## 0.8.9 (February 2026)

### New features
- **Panel system**: Control panel layout and organization
  - Flexible panel positioning (left, right, top, bottom)
  - Detached control panels for separate windows
  - Nested panels and subpanels support
  - Grouped controls within panels
  - Improved spacing and borders for better visual organization
  - Full backend support (Qt, Gradio, matplotlib, notebook)
- **Table data type**: Display tabular data natively
  - Core Table functionality without external dependencies
  - Optional pandas DataFrame support for advanced use cases
  - Rendering support across all backends (Qt, Gradio, matplotlib)
  - Headerless tables option
- **TimeControl enhancements**: Better time-based parameter control
  - Improved slider help display
  - Additional demos showcasing time-based animations

### API improvements
- Context support at pipeline initialization
- Backend selection via enum (string format still supported)
- Graph visualization for GUI pipelines (press `G`)

### Deprecations
- Decorator syntax (`@interactive(param=(default, [min, max]))`) is the recommended way to declare controls. The inline tuple shorthand in function defaults remains supported and emits no warning (this entry previously announced a deprecation that was never enforced).
- `output_canvas` argument removed
- Context aliases (`global_params`, `states` etc...) deprecated at initialization

## 0.8.8 (January 2026)

### New features
- **Clean context API**: Access shared context directly without `global_params` pollution
  - `get_context()` - Get the shared context dictionary
  - `context` - Direct dict-like access to context
  - `layout` - Access layout configuration directly
  - `audio` - Access audio functionality directly

### Code quality improvements
- Replaced all assertions with proper exceptions (`ValueError`, `TypeError`, `RuntimeError`)
- Fixed all mutable default arguments across the codebase (prevents shared state bugs)
- Improved type hints with proper `Optional` and `Any` types
- Better error messages for debugging

### UX improvements
- Dropdown menus are now hidden when only a single choice is available
- Helpful message displayed when Graphviz is not available (when pressing `G`)
- Fixed warning in linestyle for curves

### Bug fixes
- Fixed audio initialization order in Qt backend
- Fixed pytest failures for optional dependencies in CI
- Fixed various edge cases in error handling

### License
- Updated to MIT License

## History
- Interactive pipe was initially developed by [Balthazar Neveu](https://github.com/balthazarneveu) as part of the [irdrone project](https://github.com/wisescootering/infrareddrone/tree/master/interactive) based on matplotlib.
- Later, more contributions were also made by [Giuseppe Moschetti](https://github.com/g-moschetti) and Sylvain Leroy.
- August 2023: rewriting the whole core and supporting several graphical backends!
- September 2024: Gradio backend
- January 2026: Clean context API and code quality improvements (v0.8.8)
- February 2026: Panel system and Table support (v0.8.9)
- July 2026: Removal of the legacy `global_params` injection in favor of the context API (v0.9.0)
