# Changelog

## Unreleased

### New features
- **Dear PyGui backend (`gui="dpg"`)**: a GPU-rendered window built on [Dear PyGui](https://github.com/hoffstadt/DearPyGui) (`pip install "interactive-pipe[dpg]"`). Same declarative feature set as Qt — sliders, checkboxes, dropdowns, text prompts, rangeless numeric inputs, image buttons, knobs for `CircularControl`, panels at any position (nested, collapsible, detached), keyboard shortcuts and `KeyboardControl`, `TimeControl` animations, live layout changes — with images uploaded as raw float textures, native zoomable plots for `Curve` outputs and native tables. The `auto` backend picks it after Qt and before matplotlib. No audio playback.

### Improvements & bug fixes
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

@interactive(brightness=(0.5, [0., 1.]))
def apply_brightness(img: np.ndarray, brightness: float = 0.5, global_params={}):
    global_params["brightness"] = brightness  # Storing shared data
    global_params["__output_styles"]["output"] = {"title": "Brightened"}  # Setting layout
    return img * brightness

# NEW (recommended) - using context and layout proxies
from interactive_pipe import interactive, context, layout

@interactive(brightness=(0.5, [0., 1.]))
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
