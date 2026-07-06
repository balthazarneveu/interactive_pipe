# Tech debt backlog

Findings from the July 2026 full-codebase audit (v0.9.0 refresh) that were
**deliberately deferred**. Each item is self-contained so it can be picked up
independently (by a contributor or an agent). Line numbers are valid as of
v0.9.0 — re-grep the anchors before editing.

Context: the 0.9.0 refresh already removed the legacy `global_params={}`
injection API (now raises `TypeError`, see `REMOVED_CONTEXT_KWARGS` in
`src/interactive_pipe/core/context.py`), fixed 12 bugs, converted asserts to
exceptions, and moved diagnostics to `logging`. What remains below is
structural work.

Ground rules for any item (from CLAUDE.md): run
`./venv/bin/python -m ruff format . && ./venv/bin/python -m ruff check --fix .`
and `./venv/bin/python -m pytest test/ -v --tb=short` before each commit;
small focused commits; pipeline functions must contain only function calls.

## 1. Split the GUI god files

- `src/interactive_pipe/graphical/qt_gui.py` — 976 lines. Contains
  `CollapsibleBox`, `DetachedPanelWindow`, the main window, audio player glue,
  and widget updating. Notable long functions: `update_image` (~100 lines,
  around L840).
- `src/interactive_pipe/graphical/gradio_gui.py` — 651 lines;
  `instantiate_gradio_interface` is ~220 lines (around L260).
- Suggested cut: extract panel/collapsible widgets, audio player wrapper, and
  image-conversion helpers into separate modules; break the two mega-functions
  into per-widget-type builders.
- Risk: no automated GUI tests exist — manual smoke of `demo/panel_demo.py`,
  `demo/detached_panel_demo.py`, `demo/jukebox_demo.py` (audio) required.

## 2. Decouple GUI from pipeline internals

- `src/interactive_pipe/graphical/gui.py:62-66` stores the GUI app and the
  pipeline itself inside `pipeline.global_params` (`__app`, `__pipeline`,
  `__output_styles`, `__events`) — a reference cycle and stringly-typed
  contract consumed by `core/context.py` proxies and backends.
- `gui.py:95` mutates the private `pipeline._user_context` directly.
- Suggested direction: a small typed `FrameworkState` object owned by the
  pipeline, with explicit accessors the proxies and GUIs use; keep the dict
  only as a compatibility view if needed.
- This is the largest refactor here; do it after (or together with) item 1.

## 3. Broad `except Exception` sweep (15 sites)

Sites (as of 0.9.0): `core/engine.py:160`, `helper/filter_decorator.py:54`,
`helper/choose_backend.py:19,26,31`, `helper/keyword_args_analyzer.py:33,36`,
`headless/pipeline.py:182,278,354,415`, `graphical/gui.py:251`,
`graphical/mpl_gui.py:51`, `graphical/gradio_gui.py:71,455`.
For each: decide whether to narrow the exception type, let it propagate, or
keep the swallow but log with `logging.exception` (stack trace) instead of a
bare warning. The `choose_backend` probes and `engine.py:160` (FilterError
wrapping) are intentional — annotate rather than change.

## 4. Control registry collisions & reset asymmetry

- `headless/control.py:16` — `Control._registry` is keyed by bare
  `func.__name__`: two same-named filters in different modules collide.
  Consider keying by `f"{func.__module__}.{func.__qualname__}"`.
- `helper/_private.py:1` — `registered_controls_names` (global mutable list)
  is reset by `@interact` (`filter_decorator.py:89`) but never by
  `@interactive`, so control-name uniqueness errors can accumulate across
  repeated decoration in one process (e.g. notebooks re-running cells).
  Decide on a single reset point (probably pipeline construction).
- Related: `Control._panel_cache` (control.py:17) is never cleared.

## 5. Blocking `input()` prompt in library path

`data_objects/data.py:75-76` — `Data.check_path(None)` falls back to
`prompt_file()` → `input()`. Load-bearing for the GUI key bindings
(`graphical/gui.py:220-235`, save/load parameters), but a headless pipeline
calling `.save()` without a path silently blocks on stdin. Suggested fix:
raise `ValueError` by default and pass an explicit `prompt=True` only from the
GUI call sites.

## 6. Qt SIGINT/SIGTERM reset

`helper/choose_backend.py:42-43` resets both handlers to `SIG_DFL` when the Qt
backend is selected (deliberate: makes Ctrl-C kill the Qt app). It still
clobbers host-application handlers. If revisited: save/restore around the Qt
event loop, or make it opt-out.

## 7. Smaller items

- Builtin shadowing: `filter` used as a variable name in `core/pipeline.py`
  (~L55,83,97), `headless/pipeline.py:103,110`, `headless/control.py:207`.
- `data_objects/data.py:132` `load_binary` unpickles arbitrary files —
  docstring warning added in 0.9.0; consider refusing by default or
  restricting to app-controlled paths.
- `isinstance(x, A) or isinstance(x, B)` → tuple form leftovers in
  `data_objects/curves.py` and scattered singles.
- Pre-existing pyright error: `graphical/mpl_gui.py:197` (`len()` on
  `Unknown | None`) — pyright is informational per CLAUDE.md.
- `data_objects/audio.py:19` module-level `__iter_audio_player` global with
  misleading dunder naming; `headless/pipeline.py:58` name-mangled keyword
  param `__routing_by_indexes`.
- Doc/status contradiction (user decision pending): readme changelog (0.8.9
  notes) says inline tuple syntax is deprecated, but the code emits no warning
  and `doc/inline_syntax.md` presents it as a supported style. Decide:
  un-deprecate (drop the changelog claim) or add a real `DeprecationWarning`.

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
