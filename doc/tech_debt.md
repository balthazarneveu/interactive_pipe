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

### 1. Unreachable PySide6 fallback (behavior decision pending)

`src/interactive_pipe/graphical/qt_backend.py` — the PyQt5 `except ImportError`
branch raises `ModuleNotFoundError("No PyQt")` before the PySide6 block can
ever run, so a PySide6-only machine cannot use the Qt backend. The block was
moved verbatim (with a NOTE) during the split. Fixing it means moving the
raise after the PySide6 attempt — a behavior change on PyQt-less machines
that cannot be tested locally (only PyQt6 is installed in ./venv).

### 2. Gradio double launch

`InteractivePipeGradio.run` launches the Blocks app twice: once via
`instantiate_gradio_interface` (build + launch wrapper) and again via
`MainWindow.refresh()`. The build/launch split
(`build_interface()`/`launch()` in `graphical/gradio_gui.py`) makes
consolidation easy, but the call count is pinned by
`test/test_smoke_gradio.py` on purpose — collapsing to a single launch is a
behavior change that needs manual verification against a real browser
session.

### 3. Key-bound events have no filter-facing reader

`InteractivePipeGUI.bind_key_to_context` writes into
`pipeline.framework_state.events`, but since the 0.9.0 injection removal no
proxy exposes events to filters — the feature is unreachable from user code
(the F1 help text used to advertise `context['__event'][...]`, which no
longer exists). Candidate fix: an `events` proxy in `core/context.py`
mirroring `layout`/`audio`, plus a demo. Alternatively remove the event
machinery from `gui.py` altogether.

### 4. Doc/status contradiction on inline tuple syntax (untouched by decision)

readme changelog (0.8.9 notes) says inline tuple syntax is deprecated, but
the code emits no warning and `doc/inline_syntax.md` presents it as a
supported style. Deliberately left as-is in the July 2026 pass (user
decision: ignore). If revisited: truly deprecating is awkward because
`control_from_tuple` is shared with the recommended decorator-kwarg syntax —
un-deprecating (dropping the readme claim) is the cheap consistent option.

### 5. Repeated-filter controls only drive the first instance

Pinned (not fixed) by
`test/test_control_registry.py::test_repeated_filter_keeps_single_control_on_first_instance`:
when one decorated filter is used twice in a pipeline, its registered
controls connect to the first instance only; the repeat runs with default
values. Supporting live controls on repeated filters needs per-instance
Control cloning at pipeline construction.

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
