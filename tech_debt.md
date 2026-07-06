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

### 1. Doc/status contradiction on inline tuple syntax (untouched by decision)

CHANGELOG (0.8.9 notes) says inline tuple syntax is deprecated, but the code
emits no warning. The standalone inline-syntax doc page was removed from the
docs site in July 2026 (too niche); the tuple shorthand is still shown as
supported in the controls guide. If revisited: truly deprecating is awkward
because `control_from_tuple` is shared with the recommended decorator-kwarg
syntax — un-deprecating (dropping the changelog claim) is the cheap
consistent option.

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
