# Tech debt backlog

Findings from the July 2026 full-codebase audit (v0.9.0 refresh) that are
**deliberately deferred**. Each item is self-contained so it can be picked up
independently (by a contributor or an agent). Re-grep the anchors before
editing.

Context: the 0.9.0 refresh removed the legacy `global_params={}` injection
API, fixed 12 bugs, converted asserts to exceptions, and moved diagnostics to
`logging`. The July 2026 cleanup pass (see "Done" below) then worked through
the structural items: the GUI god files are split, the framework state is a
typed object, the exception sweep / control registry / blocking-input items
are resolved, and offscreen GUI smoke tests now exist
(`test/test_smoke_qt.py`, `test_smoke_gradio.py`, `test_smoke_mpl.py`).

Ground rules for any item (from CLAUDE.md): run
`./venv/bin/python -m ruff format . && ./venv/bin/python -m ruff check --fix .`
and `./venv/bin/python -m pytest test/ -v --tb=short` before each commit;
small focused commits; pipeline functions must contain only function calls.

## Open items

From the November 2026 consolidation review (judgement calls, see
`plan_consolidate.md` Status for reproducers):

- **Unassigned call to a filter returning a value raises** (`f(img)` alone in
  a pipeline body, `f` returning an array): `FilterError ... unpacks 0
  values`. Same in 0.9.4. Python would drop the value; dropping it would also
  hide a forgotten assignment. Decide and document.
- **`params=` (snapshot / sweep, flat `{name: value}`) vs `parameters=`
  (pipeline call, nested `{filter: {param: value}}`)**, `output=` (snapshot /
  sweep) vs `output_indexes=` (`save`): names to align before the release.
- **`DisplayError`** is raised to users but not exported from
  `interactive_pipe` (`interactive_pipe.graphical.display.DisplayError`).
- **`save()` has its own image normalisation** (`headless/pipeline.py::_as_image_array`,
  keeps RGBA for PNG) next to `graphical/display.normalize_image` (composites
  RGBA for display): different purposes, same dtype rules written twice.
- **A figure laid out by the user (`fig.tight_layout()` at its `figsize`) is
  not laid out again** when drawn at cell size: labels can be cut. Only a
  figure with default margins gets `tight_layout` at the drawn size.

From the November 2026 code audit (branch `audit/code-quality`; confirmed by
a reproducer unless marked *by reading*). The fixed findings are in the
changelog and `test/test_audit_*.py`; these were left because they need a
design decision or a larger change:

- **A `FilterCore` instance is rewired in place** (`core/graph.py` call
  entry, `headless/pipeline.py::from_function`): `a = flt(img); b = flt(a)`
  with a `FilterCore` object raises `KeyError`, and a `FilterCore` shared by
  two pipelines breaks the first one. Copy per call site or raise on reuse.
  (`@interactive` functions are not concerned.)
- **Cached runs return the cache's own buffers** (`core/engine.py`,
  `cache.py`): mutating a returned array changes what the next cached call
  returns. Read-only views or a copy on the way out (cost to measure).
- **Plain tuple / list defaults become sliders** in an `@interactive`
  signature (`def blur(img, size=(3, 3))` receives `size=3`): the ultra-short
  shorthand fires on data defaults. At least reject `min == max`.
- **`@interact` dry run uses the raw signature defaults** (the tuple, not the
  control value) to count outputs: a multi-output filter can lose outputs.
- **`None` inside a returned grid is dropped** (`return [[a, None], [b, a]]`
  gives a ragged layout): keep it as an empty cell or reject it.
- **`check` / `describe` print the control's value after the run was
  restored** (`gain = 1` next to outputs computed with the script's
  `gain=2.0`, pinned by `test_check_command.py::test_good_script`): decide
  whether the report shows the declared or the used value.
- **`--max-calls` does not count skipped calls** (`--pipeline second` on a
  script looping over `first`), and **sweep labels show the requested value**
  when the control clamps it (only a warning says so).
- **`run_script` does not restore `os.chdir` / `os.environ` writes made by
  the script**.
- **An output going from an array to `None` keeps its last image** on screen
  (`graphical/window.py::set_images`); an unsupported output type logs a
  warning on every refresh.
- **Qt: a `threaded=True` GUI is no longer threaded on a second `run()`**
  (`closeEvent` stops the runner); `FloatSpinBoxControl` shows 4 decimals.
- **DPG (by reading): key, menu and file-dialog callbacks call `refresh()`
  on Dear PyGui's worker thread** while the render loop may run the pipeline
  too; Qt serialises runs with `_run_lock`. Route them through
  `request_refresh()`.
- **Qt (by reading): `_refit_figure` takes the run lock on the GUI thread**:
  resizing during a slow threaded run freezes the window until it ends.
- **`MainWindow.error_cell_positions` (Qt) duplicates the base method**;
  `reset_parameters` is identical in the Qt and DPG GUIs.
- **Gradio: the icon-button choice goes back to its default** on any other
  event (`gradio_layout.py::collect_changing_inputs` passes a constant
  `gr.State`). `TickBoxControl.reset` calls the removed `component.update`.
- **`Data.save(path, override=False)` checks `path` but writes
  `stem + title`**: the titled file is overwritten (`Image`, `Audio`).
- **`data_objects/audio.py`** (wavio, not installed, *by reading*): `.mp3` /
  `.mp4` listed but only WAV is read / written, no clipping before the int16
  cast, `np.int64` rates rejected. `sound.load` covers the same ground.
- **`sound.load(mono=False)` on a non-WAV file is mono** (ffmpeg is called
  with `-ac 1`); `resample` to under one sample raises numpy's FFT error.
- **`Video`: `cv2.VideoCapture` and GIF handles are never released**;
  `thumbnail` fails on `(T, H, W, 1)` uint8; a 2D `.npy` is accepted.
- **`draw.points(radius=1e7)`** is not clamped like coordinates (30 s);
  **`Table`**: ragged rows raise `IndexError`, a headerless table comes back
  from CSV with `Unnamed: 0` columns.
- **Curve update keeps a removed label / style / xlim** from the previous
  plot (only the data and the axes limits follow).
- **Notebook `refresh`** has no `FilterError` handling (raw traceback).

## Done in the October 2026 review pass (don't redo)

- **Inline tuple syntax status (former item 1)**: un-deprecated. The 0.8.9
  changelog entry now says the decorator syntax is recommended and the tuple
  shorthand stays supported without warning (`control_from_tuple` serves both).
- **Qt import cascade**: `qt_control.py` imports its symbols from
  `qt_backend.py` (single cascade) and stays importable without a Qt binding
  by catching the `ModuleNotFoundError`.
- **`MainWindow.size` shadowed `QWidget.size()`**: the window-level request
  is now `window_size` on every backend window; `InteractivePipeGUI.size`
  (the user-facing kwarg) is unchanged. `InteractivePipeGUI.help` is
  `show_help` (the old name is kept as an alias).

## Done in the July 2026 follow-up pass (don't redo)

- **PySide6 fallback reachable**: `qt_backend.py` now warns (instead of
  raising) when PyQt5 is missing, tries PySide6, and only then raises
  `ModuleNotFoundError("No PyQt")` — same cascade as `qt_control.py`;
  `choose_backend.py` still gets the error on a binding-less machine.
  Subprocess tests in `test/test_qt_backend_cascade.py` pin both paths.
- **Gradio single launch**: `InteractivePipeGradio.run` launches the Blocks
  app exactly once (the launching `MainWindow.refresh()` is gone; the second
  launch also dropped the share flag). Verified against a real local server;
  `test/test_smoke_gradio.py` pins one launch call carrying `share=`.
- **`events` proxy**: filters read key-bound context events via
  `from interactive_pipe import events` (`events.get(name)` is False when
  unbound, so filters also run headless). Demo: `demo/key_event_demo.py`;
  Qt round-trip test in `test/test_smoke_qt.py`.
- **Per-instance controls on repeated filters**: `from_function` clones
  registered controls for each repeat (`Control.clone_unconnected`, names
  suffixed like the filter: `amount` → `amount_1`), and the `@interactive`
  wrapper lets engine-passed kwargs win over registered control values (it
  used to clobber them, making repeats mirror the first slider). Key/timer
  bound controls (KeyboardControl/TimeControl) stay on the first instance —
  their key bindings would collide — pinned in
  `test/test_control_registry.py`.

## Done in the July 2026 cleanup pass (don't redo)

- **Split the GUI god files (item 1)**: `qt_gui.py` 976 → ~520 lines with
  `qt_backend.py` (binding detection), `qt_widgets.py` (CollapsibleBox,
  DetachedPanelWindow), `qt_audio.py` (QtAudioPlayer), `qt_image.py`
  (numpy→pixmap, 1D fallback, curve/table cells), `qt_panels.py`
  (QtPanelBuilder); `gradio_gui.py` 651 → ~385 lines with
  `gradio_outputs.py` (per-type build/convert dispatchers) and
  `gradio_layout.py` (panel/grid/slider rendering, event binding), closures
  → methods, `build_interface`/`launch` split. `qt_gui`/`gradio_gui` remain
  the public facades (re-exports kept).
- **Decoupled GUI from pipeline internals (item 2)**:
  `core/framework_state.py` — typed `FrameworkState` (output_styles, events,
  AudioBindings, weakref pipeline backref) owned by the pipeline; the magic
  `__`-keys are gone (`__app`/`__window`/`__player`/`__audio` deleted
  outright — they were write-only). `global_params` remains the user
  shared-state dict only. `PipelineCore.update_user_context` replaced direct
  `_user_context` pokes.
- **Broad `except Exception` sweep (item 3)**: narrowed (choose_backend
  probes, tuple-conversion fallbacks, graphviz import, gradio markdown
  probe), upgraded to `logging.exception` (routing deduction, import_tuning,
  batch save), or comment-annotated as deliberate (engine FilterError wrap,
  GUI graph feedback, mpl fullscreen, gradio shallow-copy).
- **Control registry (item 4)**: `Control._registry` keyed by
  module + qualname; name uniqueness scoped per decorated function (fixes
  notebook re-runs AND the inability of two filters to share a parameter
  name); duplicate control names across a pipeline raise at
  `from_function`; `_panel_cache` documented as process-wide by design.
  Tests in `test/test_control_registry.py`.
- **Blocking `input()` (item 5)**: `Data.check_path(None)` raises
  `ValueError`; `prompt_file()` stays for the GUI key bindings that call it
  explicitly.
- **Qt SIGINT/SIGTERM reset (item 6)**: annotated as deliberate in
  `helper/choose_backend.py` (Ctrl-C must kill the Qt app); save/restore
  variant still deferred.
- **Smaller items (item 7)**: builtin `filter` shadowing renamed; pickle
  `load_binary` gated behind `allow_pickle=True` (internal callers opt in);
  `isinstance` tuple form everywhere; mpl_gui pyright narrowing fixed (0
  pyright errors); `__iter_audio_player` → `_audio_player_counter`;
  `__routing_by_indexes` → `_routing_by_indexes`.
- **GUI smoke tests**: offscreen Qt (9 tests), launch-mocked gradio
  (15 tests), Agg matplotlib (2 tests) — pin window build, styled titles,
  parameter updates, panels/detached windows, all update_image branches,
  audio wiring and the dry-run restore.

## Done in 0.9.0 (for reference, don't redo)

Legacy injection removal + fail-loudly checks, alias removal
(`layout.set_style` etc., `Control.group`, `qt_gui.layout_obj`), wavio flag /
unbound `data_save` / unclosed handle in audio.py, string-control step
default, signature-cache name-mangling bug, `__repr__` stdout side effect,
lazy `sys.excepthook` install, deferred image-backend error + availability
validation, asserts→exceptions, print→logging, dead code
(`analyze_expected_keyboard_argument`, impossible `"context" in kwargs`
branches), typos, duplicate `KEY_PAGEDOWN`, docs refresh (readme FAQ wrong
methods, `interactive_piper` typo, stale `code_architecture.md`).
