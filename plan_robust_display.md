# Plan: tolerant display, quiet errors, clean process state, docs build

Branch `feature/robust-display`, based on `integration/next-level`. This is the consolidation round: the items below were found while reviewing the merged result of the five previous branches (read the "Left for review" parts of the Status sections of `plan_declare_less.md`, `plan_scientific_outputs.md`, `plan_agent_packaging.md` first).

## Items

1. **Display what numpy people actually return** — in `graphical/display.py::prepare_display` (the single conversion point for all backends and snapshots), so that no backend crashes and all show the same thing:
   - `(H, W, 1)` → shown as `(H, W)`; `(H, W, 4)` RGBA → composited on a checkerboard or white (decide, same everywhere); `bool` masks → 0/1; `uint8` → /255; `uint16` → /65535; other integer types: decide (clear error or scale) and document.
   - channel-first `(3, H, W)` / `(1, H, W)`, 4D batches, 0-size arrays, object arrays: cannot be guessed safely → an error naming the filter output with the fix, the same on every backend and in snapshots (today: a backend-specific crash naming nothing).
   - Then update `output_check` (the snapshot warnings added by `feature/declare-less`): cases that now display correctly everywhere must stop warning "the Qt and Dear PyGui backends raise on it"; it must know `Figure` / `Axes` / `Image` outputs.
   - Open decision from the last round, to settle with evidence: on the mpl backend a 2D array without colormap is shown with viridis while Qt, DPG, Gradio and snapshots show gray. Make gray the consistent default unless you find a reason not to; list it first in the changelog as a visible change.
   - Verify on the real backends offscreen (Qt grab, DPG if it can run headless, mpl Agg, snapshot) with one parametrised test over the array zoo.
2. **One error, once.** A failing filter prints a "PIPELINE ERROR" banner to stdout *and* raises `FilterError` carrying the same text, so a headless script or a test shows it twice (three times with logging). In headless calls, `snapshot`, `sweep` and the CLI: raise only. In a GUI event loop (where nothing catches it): show it once. Check what each backend does when a filter raises during a slider move: the window must survive and show the error (and recover on the next valid value).
3. **Error wording leftovers**
   - `@interactive(gain=(5, [0, 3]))` → say the default is outside the range (today "min=5 max=[0, 3] - max parameter should be numerical too").
   - `TypeError: Expected <class 'float'>, got <class 'str'>`-style messages anywhere a control name is available must name it; grep for remaining messages that name neither filter nor parameter.
   - `layout.style(...)` / `context[...]` outside a filter: the "Framework operation called outside of filter execution" message should say which call and show the two-line fix.
   - In the error for a wrong output count, the filter is named by its alias in the pipeline body; when the function name differs, give both.
4. **Process state**: controls are registered globally per function qualname, so (a) two scripts run in one interpreter with same-named `__main__` filters collide (`process_image: hue_shift not in ...`), (b) two pipelines built from the same filter share the control object, so a value set in one becomes the start value of the other. Fix (a). For (b) write a failing-or-passing test that documents the behaviour, then decide: per-pipeline control clones are probably right (the first round already clones for literal kwargs: `Control._clone_with_default`); if the change is too invasive for the time left, document it in the guide and Status instead.
5. **Import cost**: `import interactive_pipe` loads matplotlib (and `interactive-pipe --help` with it). Measure (`python -X importtime`), make the heavy imports lazy where it is safe, add a test that `import interactive_pipe` does not import `matplotlib.pyplot` nor any GUI toolkit, report before / after.
6. **Docs build**: `mkdocs build --strict` has never been run on these branches. If mkdocs with the project's doc dependencies fits in a throwaway venv under `/Data/` (check free space first: skip and say so if less than 2 GB would remain), build, fix every warning (broken links, pages missing from nav, bad anchors), delete the venv. Otherwise check links and nav with a small script and say what was not verified.
7. **Consistency pass** over `docs/` and `readme.md`: the five branches each added pages; make sure the same thing is not explained three times with different wording, that every public name mentioned exists (`grep` each code-formatted name against the package), and that the API reference lists the new public API (`PipelineSyntaxError`, `snapshot`, `sweep`, `describe`, `summary`, `draw`, annotation controls, `skill_path`, CLI).

## Ownership

Yours: `src/interactive_pipe/graphical/display.py`, `headless/snapshot.py`, `headless/explore.py`, `headless/control.py`, `core/`, `helper/`, `agent/command_line.py`, `cli.py`, `__main__.py`, `docs/` except the pages named below, `readme.md`, `mkdocs.yml`.
Not yours: event handling and widgets in `graphical/*_gui.py`, `*_control.py`, `qt_image.py`, `qt_viewer.py`, `dpg_*.py`, `mpl_window.py`, `gradio_*.py` (the pointer-input agent rewrites parts of them: for item 2 keep your edits there to the few lines that catch and show the error); the skill files and `demo/gallery/`, `docs/gallery.md` (the dogfooding agent); `docs/guide/mouse-input.md`.

## Rules (same as the previous rounds)

- Work only in this worktree and on this branch. Never push, open a PR, merge into another branch, bump the version, publish, or comment on GitHub.
- This worktree has no `venv/`. Before any python command:
  `export PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg; PY=/home/bneveu/code/interactive_pipe/venv/bin/python`
  Do not `pip install` anything into that shared venv. Both disks are nearly full: no new venv or large download on `/`; a throwaway venv, if truly needed, goes under `/Data/` and is deleted afterwards.
- Follow `CLAUDE.md`: ruff format + `ruff check --fix` + the full pytest suite before each commit; small focused commits with their tests; no `assert` for validation; no mutable defaults.
- Every change needs a test. Every visual change must be looked at: render a PNG (snapshot, or an offscreen Qt grab) and read it.
- Shared files (`CHANGELOG.md` "Unreleased", `src/interactive_pipe/__init__.py`, `mkdocs.yml`, `CLAUDE.md`): add only, keep the edit minimal; two other agents edit them in parallel on sibling branches.
- Stay inside the files listed under "Ownership". If you find a bug in a file you do not own, write it in Status under "Left for review" with a reproducer instead of fixing it.
- Hard stop at 11:30 CET (check `date`). Stop earlier when the plan is done. At the end: clean tree, green suite, and a "Status" section at the bottom of this file saying what was done (commit hashes), what was not, and what is left for review. Then stop; do not start unplanned work.

## Status

**Summary (04:00 CET):** all seven items done on `feature/robust-display`
(`fb43763`..HEAD, nothing pushed, no PR, no merge, no version bump). Final
state: `1334 passed, 6 skipped` (baseline `1216 passed, 6 skipped`), ruff
format/check clean, pyright 8 errors — the pre-existing ones in
`graphical/qt_control.py` (7) and `graphical/dpg_panels.py` (1). The throwaway
docs venv under `/Data/` was deleted.

Commits: item 1 `d8a758c`, item 2 `dc7a10e` (+ `d2853f0`), item 3 `0809717`,
item 4 `e03fcc5`, item 5 `d22f84a` (+ `9c00303`), items 6-7 `9adb6e9`, and the
commit adding this section.

Agent run of 2026-11-14, started 03:20 CET, autonomous. Environment check: the
shared interpreter imports `interactive_pipe` from this worktree's `src/`;
baseline reproduced before any change.

### 1. Tolerant display — done (`d8a758c`)

- Before (probed on the real backends, offscreen): Qt raised on `(H, W, 1)`,
  RGBA, `(3, H, W)`, `(1, H, W)`, 4D, object, 2-channel arrays (`Expected
  3-channel image, got 16 channels`); Dear PyGui on all of those except RGBA;
  mpl on channel-first / 4D / object / 2-channel (`Invalid shape (3, 12, 16)
  for image data`); the snapshot drew everything (placeholders). Integer images
  were clipped (white) by the GUIs.
- `prepare_display(content, style, name, filter_name)` now turns every 2D/3D
  array into an `(H, W, 3)` float image (`normalize_image`): `(H, W, 1)` ->
  `(H, W)`; `bool` -> 0/1; `uint8` / 255; `uint16` / 65535; **other integer
  types are taken as values like floats** (decision: a `0`/`1` int mask is a
  common idiom and must not raise; 0-255 data in `int64` is clipped and
  `output_check` warns with the fix); RGBA composited on a **gray
  checkerboard** (decision: shows transparency as such; squares of 1/32 of the
  largest side, >= 4 px; figures stay composited on white as before). Float
  RGB arrays are returned as is (no copy); 1D arrays stay signals.
- Channel-first, 4D, 0-D, empty, complex, object/string and 2- or >4-channel
  arrays raise `DisplayError(ValueError)`: `output 'out' (returned by filter
  'produce') cannot be displayed: channel-first array (3, 12, 16). Fix: move the
  channels last: np.moveaxis(img, 0, -1).` — raised by `snapshot` / `sweep`;
  in a GUI window `InteractivePipeWindow._styled` shows it in the cell as text
  (every backend draws text), logs it once per cell, and the cell recovers on
  the next valid output.
- **Gray vs viridis, settled: gray everywhere.** Evidence: Qt, DPG, Gradio and
  snapshots showed gray; mpl's `imshow` applied viridis *and* fixed its colour
  limits on the first frame (`set_data` keeps the clim), so a 2D output whose
  range changed with a slider was misdisplayed. 2D arrays now reach every
  backend as gray RGB, which needed no change in `mpl_window.py`. First bullet
  of the CHANGELOG "Changes that can affect existing code".
- `output_check`: checks the raw output (`SnapshotCell.raw`, new field), not
  the converted one; unsupported arrays come from the same
  `display.array_display_problem` as the error; the "gui" severity ("the Qt and
  Dear PyGui backends raise on it") is gone; `Figure` / `Axes` / `Image` are
  known outputs (an `Image` is checked by its array).
- Tests: `test/test_display_zoo.py` — one zoo (11 displayable, 7 not) over Qt
  (pixmap pixels), DPG (texture buffer, runs headless), mpl (axes image, must
  be RGB), Gradio (converted output) and snapshot: same pixels within one
  uint8 level everywhere, same error text everywhere, logged once, recovery.
  Looked at: a snapshot of the zoo, an offscreen Qt grab and the mpl figure
  (gray, checkerboard, error text in the cell).
- Docs: "What a filter can return" in `guide/figures-and-overlays.md`.

### 2. One error, once — done (`dc7a10e`, `d2853f0`)

- The engine no longer prints the `PIPELINE ERROR` banner before raising.
  Headless calls, `snapshot`, `sweep`, tests and the CLI: raise only (the CLI
  prints the script's traceback once). Uncaught in a script: the excepthook
  prints the banner once (+ the `INTERACTIVE_PIPE_DEBUG=1` hint; with it, the
  full traceback once).
- GUI event loop: `InteractivePipeWindow.report_error` prints the banner once
  per distinct error (not again on every slider move while it keeps failing;
  again after a successful run). One line added in each backend's
  `show_error` (Qt, DPG, mpl/nb); Gradio: `FilterError` -> `gr.Error(message)`
  so the page shows the message (it showed a generic "Error") and the app
  keeps running. Checked: Qt, DPG and mpl windows survive three failing
  refreshes, show the error and recover; Gradio raises `gr.Error` and recovers.
- Found on the way: `@interact`'s dry run logged a failing filter with a full
  traceback before the GUI run reported it again: now a debug message.
- Tests: `test/test_error_once.py`.

### 3. Error wording — done (`0809717`)

- `@interactive(gain=(5, [0, 3]))` now reads `@interactive filter 'f',
  parameter 'gain': Cannot create a control from gain=(5, [0, 3]): the default
  5 is outside the range [0, 3]: choose a default between 0 and 3, or widen the
  range` (the "max parameter should be numerical too" part was already fixed
  by `feature/declare-less`; the "value_default ... must be within
  value_range" wording is replaced). Same for `RangeControl`, dropdown
  defaults and values (`control 'style': 'SHINY' is not one of the choices
  [...]`), `RangeControl` value errors and the wrong-type default name the
  control when it has a name.
- Outside a filter: `layout.style('heat', ...) called outside of filter
  execution: ... Move the call into a filter:` followed by the
  `@interactive()` / `def my_filter(img):` / the call. Each proxy method names
  its own call (`context['k'] = ...`, `context.k`, `events['boost']`,
  `audio.play()`, `ctx = get_context()`).
- Wrong output count / missing `return` when the pipeline calls the filter by
  another name: `filter 'split' (function 'two_values') returned 2 values ...`;
  the fix keeps the name of the pipeline line.
- grep for messages naming neither filter nor control: the remaining ones in
  my files are internal invariants; those in `*_control.py` are listed below.

### 4. Process state — (a) fixed, (b) documented (`e03fcc5`)

- (a) Reproduced (`filter 'process_image' has no parameter 'hue_shift'` after
  `runpy` of two `__main__` scripts defining `process_image`). Controls now
  live on the (unwrapped) function object (`__interactive_pipe_controls__`),
  `Control._registry` is only the fallback for callables without attributes.
  Also fixes filters made by a factory (same qualname). Re-decoration still
  starts clean (`Control.clear_controls`). Controls die with their function
  (no leak when a notebook cell is re-run).
- (b) Test `test_pipelines_built_from_one_filter_share_its_control` documents
  the current behaviour (shared control object, start value = last value,
  direct calls too). **Not changed**: per-pipeline clones would make the Qt,
  DPG and Gradio panel builders (`qt_panels.py`, `dpg_panels.py`,
  `gradio_layout.py`, not mine) show duplicate widgets, because they build
  panel widgets from the process-wide `Panel._controls` list, which every
  clone joins (`_clone_unconnected` registers it). Documented in
  `guide/controls.md` ("One control per filter"), with the workarounds
  (literal keyword argument in the body, tuning file, `ctrl.reset()`).

### 5. Import cost — done (`d22f84a`, `9c00303`)

- Measured (`python -X importtime`, wall clock min of 5 on this machine):
  before `import interactive_pipe` 1.0 s (importtime 851 ms: `matplotlib.pyplot`
  455 ms from `data_objects/curves.py` and `image.py`, pandas 178 ms, cv2 25
  ms), `interactive-pipe --help` 1.05 s. After: 0.22 s (233 ms, of which numpy
  ~137 ms), `--help` 0.3 s.
- Availability is checked with `importlib.util.find_spec`, modules imported on
  use: `data_objects/curves.py` (pyplot, pandas; `Curve` image export uses the
  `Figure` object API, no pyplot), `image.py` (cv2, Pillow, pyplot for
  `show`), `table.py` (pandas), `headless/snapshot.py` (Figure / Agg).
- Test: `test/test_import_cost.py` (no `matplotlib.pyplot`, Qt, DPG, Gradio,
  ipywidgets, cv2 nor pandas after `import interactive_pipe` or building the
  CLI parser; image save/load, curve save and `Table.as_dataframe` still work).

### 6. Docs build — done (`9adb6e9`)

- 15 GB free on `/Data`: throwaway venv there (mkdocs-material,
  mkdocstrings[python], mkdocs-llmstxt; 190 MB with the pip cache), deleted at
  the end. `mkdocs build --strict` passed as is; also run with the nav /
  link / anchor / absolute-link validations raised to warnings (checked to
  catch an injected broken link and anchor): clean. After the item-7 pages,
  two griffe warnings came up: fixed the `sweep` docstring (one entry per
  parameter) and set `docstring_options.warn_missing_types: false` in
  `mkdocs.yml` (untyped `save_entire_buffer` in `headless/pipeline.py`, not
  mine). Final strict build clean.

### 7. Consistency pass — done (`9adb6e9`)

- Every code-formatted name in `docs/` and `readme.md` was checked against the
  identifiers of `src/` (AST) and the docs' own code blocks: all resolve (the
  rest are demo file names — all exist —, `ip.` aliases and matplotlib API).
- API reference: new pages Pipelines (`interactive`, `interactive_pipeline`,
  `interact`, `HeadlessPipeline` with `snapshot` / `sweep` / `describe` /
  `summary` / `save` / tuning, `export_animation`, `PipelineSyntaxError`,
  `FilterError`, `DisplayError`), Drawing on images (`draw`), Command line &
  skill (`skill_path`, the commands); controls page lists the annotation forms.
- Overlaps reviewed: snapshot / `INTERACTIVE_PIPE_SNAPSHOT` / agent loop are
  explained once (`guide/snapshots.md`) and referenced elsewhere; added the
  missing cross-link to `interactive-pipe snapshot`. `index.md` and the readme
  now mention figures / heatmaps / draw and annotation controls; demo count
  17 -> 19; `export_animation`'s input rule points to the shared display rules.

### Ownership notes

- Edited outside the listed files because the item required it:
  `graphical/window.py` (shared base of the backends, listed by nobody:
  `_styled` error cell, `report_error`), `data_objects/{curves,image,table}.py`
  (item 5's heavy imports live there), `headless/output_check.py` (item 1 asks
  for it). In GUI files only the catch-and-show lines of item 2: one line in
  each `show_error` (`qt_gui.py`, `dpg_gui.py`, `mpl_window.py`) and the
  `try/except` around `pipeline.run()` in `gradio_gui.py`.
- Shared files, additive edits only: `CHANGELOG.md` (one bullet first in
  "Changes that can affect existing code", own "Robust display and quieter
  errors" subsection at the end of Unreleased), `mkdocs.yml` (3 nav entries,
  one handler option). `__init__.py` and `CLAUDE.md` untouched.

### Left for review

- **Per-pipeline controls (item 4b)**: needs the panel builders to iterate the
  window's own controls instead of `Panel._controls` (`qt_panels.py:78`,
  `dpg_panels.py:109,128`, `gradio_layout.py:101`), then cloning every
  registered control in `HeadlessPipeline.from_function` (as repeats already
  are). Reproducer: `test_pipelines_built_from_one_filter_share_its_control`.
- Skill (`src/interactive_pipe/agent/build-interactive-pipeline/SKILL.md`, not
  mine): line ~106 lists displayable outputs as "float `[0, 1]`, uint8, `(H, W)`
  or `(H, W, 3)`" (RGBA, `(H, W, 1)`, uint16, bool, figures are fine now);
  the error table row ~212 quotes the old `min=5 max=[0, 3]` /
  `value_default 5 must be within value_range` messages.
- `gradio_control.py` / `nb_control.py`: `TypeError: Expected int control
  type, got <class 'float'>`-style messages name no control (factory
  invariants, rarely user-facing).
- `mpl_window.py`: text cells (errors, `str` outputs) are not wrapped; the
  display error is pre-wrapped at 36 characters in `window._styled` as a
  workaround.
- `headless/animation.py`: calls `prepare_display` without the output / filter
  name, so a `DisplayError` there says "output" only.
- `headless/pipeline.py`: `HeadlessPipeline.__call__` has no docstring (the
  API page shows the signature only); `save_entire_buffer` is untyped.
- Flaky, pre-existing: `test/test_command_line.py::test_doctor_opens_no_window`
  failed once in a full run (a `QApplication` left alive by an earlier test,
  depending on GC timing) and passed in three reruns and alone.
