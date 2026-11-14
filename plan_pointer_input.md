# Plan: mouse input — click a point, drag a region

Branch `feature/pointer-input`, based on `integration/next-level` (everything from the previous rounds is merged there).

## Why

Scientific visual debugging constantly needs "this pixel" and "this region": seed of a region growing, the row whose profile is plotted, the patch whose spectrum is shown, a crop to zoom on. Today the user has to add two or four sliders. The design note at the end of `plan_scientific_outputs.md` ("Design note: mouse input") is the starting point: read it first, it lists what each backend already has.

## What to build

1. **Controls** `PointControl` and `RegionControl`, exported from `interactive_pipe`:
   ```python
   @interactive(seed=PointControl((0.5, 0.5), on="img"))  # (x, y)
   def region_grow(img, seed=(0.5, 0.5)): ...


   @interactive(roi=RegionControl((0.25, 0.25, 0.75, 0.75), on="img"))  # x0, y0, x1, y1
   def crop_stats(img, roi=(0.25, 0.25, 0.75, 0.75)): ...
   ```
   - Values are fractions of the image size in [0, 1] (so a tuning file survives a resolution change, and the value is valid before any image exists). Give the filter author a one-line way to get pixels, e.g. helpers `interactive_pipe.draw.to_pixels(point_or_region, img)` or similar — pick the simplest and document it. Decide and justify in Status.
   - `on=` names the pipeline output that receives the gesture; default: the first image output. An unknown name fails when the pipeline is built, with the available names.
   - They are ordinary parameters everywhere else: `pipe(img, seed=(0.2, 0.4))`, `snapshot`, `sweep(seed=[(0.1, 0.1), (0.6, 0.4)])`, `describe()` (kinds `"point"` / `"region"`, with the target output), tuning export / import, value validation with clear errors (wrong length, outside [0, 1], region with x1 < x0 is reordered or rejected — decide).
   - Annotation form if it fits naturally with the existing annotation controls: `seed: Annotated[Tuple[float, float], PointControl(...)] = (0.5, 0.5)` already works through "any Control"; just test it.
2. **Backends**, in this order; each one finished (tested, looked at) before the next:
   1. matplotlib (`button_press_event`, `event.inaxes`, `xdata/ydata`),
   2. Qt (reuse `ImageView.map_to_image`; a click that moves < ~3 screen px sets the point, left-drag keeps panning; shift-drag draws a region),
   3. Dear PyGui (`image_cell_at`, `ViewState.image_rect`),
   4. Gradio (`gr.Image.select`, point only is fine),
   5. notebook: fallback only.
   - The window draws the marker / rectangle itself as an overlay (not into the filter output). Heatmaps shown with a colorbar and enlarged maps must map back to data coordinates (`display.heatmap_geometry`). For rasterised matplotlib figures, a first version may reject `on=` pointing to a figure output with a clear message.
   - Fallback wherever gestures are not available: sliders (x, y / x0, y0, x1, y1), as `KeyboardControl` falls back to a slider. The fallback must be what an unknown future backend gets by default.
   - Simulate the events in tests (Qt: `QTest.mouseClick` or direct event objects offscreen; mpl: `canvas.button_press_event` / `MouseEvent`); assert the control value and that the pipeline re-ran.
3. **Demo** `demo/pointer_demo.py`: an image, a clicked point whose row profile is plotted as a curve, and a dragged region whose crop is shown enlarged. It must run headless in `test/test_demos_headless.py` (it is picked up automatically) and give a meaningful snapshot.
4. **Docs**: `docs/guide/mouse-input.md` (added to `mkdocs.yml` nav), a short section in the packaged skill is NOT yours to write: put the 10 lines you would add to the skill in Status, they are merged later.

## Ownership

Yours: a new module for the two controls (e.g. `src/interactive_pipe/headless/pointer.py`), the control-to-widget factories and event handling in `src/interactive_pipe/graphical/` (`*_control.py`, `*_gui.py`, `qt_image.py`, `qt_viewer.py`, `dpg_viewer.py`, `dpg_image.py`, `mpl_window.py`, `gradio_*.py`, `nb_*.py`), the minimum needed in `headless/describe.py`, `demo/pointer_demo.py`, `docs/guide/mouse-input.md`, new test files.
Not yours: `graphical/display.py`, `headless/snapshot.py`, `core/`, `helper/`, the skill, `readme.md` (another agent works there). You may call into them, not edit them.

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

Done, 2026-11-14 (03:20 → ~04:00 CET). Full suite green: 1301 passed, 6 skipped (5 consecutive runs).

### Commits (in order)

| Commit | What |
|---|---|
| `3a1771b` | `headless/pointer.py`: `PointControl`, `RegionControl`, `to_pixels` (exported from `interactive_pipe`), validation, `check_targets`; `describe()` kinds `point` / `region` with `on` and `axes`; headless tests (params, sweep, tuning json/yaml, literal kwargs, `Annotated`). |
| `6161f3f` | Slider fallback for any backend without gestures (`InteractivePipeGUI.pointer_gestures = False` by default), in the control list and in panels; unknown `on=` fails when the GUI is built; fallback checked through each backend's real widget factory (mpl, Qt, DPG, Gradio, notebook) and a minimal "future" backend. |
| `88b76f8` | matplotlib: click / shift-drag (`button_press/motion/release`), heatmap colorbar mapping, toolbar pan/zoom modes keep the mouse, overlay artists (also on the notebook figure), figure target warns. |
| `3ab7751` | Qt: `ImageView` forwards gestures to a `PointerHandler` (via `map_to_image`, so zoom/pan/fit); < 3 px click sets the point, left-drag pans, shift-drag draws without panning; overlay painted by the view; F1 help lists gestures; threaded mode. |
| `4a385a3` | Dear PyGui: same gestures through the global mouse handlers and `ViewState.image_rect`; marks drawn on the cell drawlist by `place_image` (follow zoom/pan/relayout). Looked at on a real viewport (`output_frame_buffer`). |
| `27edf19` | Gradio: `gr.Image.select` sets the nearest point (event injection checked with gradio's `special_args`); regions keep sliders there (`pointer_gestures = ("point",)`); marks drawn on the displayed copy. |
| `182de2b` | Notebook: fallback sliders + marks on the figure (test). |
| `345515c` | `demo/pointer_demo.py` (row profile of the clicked point, enlarged crop of the region); picked up by `test_demos_headless.py`. |
| `7694021` | `docs/guide/mouse-input.md` (nav: Guide › Widgets › Mouse input), its code blocks run in `test/test_pointer_docs.py`; CHANGELOG "Unreleased" section. |
| `a86285a` | Unit tests of the shared gesture logic (`graphical/pointer_input.py`); DPG move events read `get_mouse_pos(local=False)` like the press. |
| (last commit) | Qt threaded-mode test waits on a 5 s deadline instead of a fixed number of event-loop passes (it failed once in a full run under load); this Status. Suite then green 5 runs in a row. |

Every visual change was looked at as a PNG: Qt offscreen grabs (fallback sliders, overlay, demo window), matplotlib `savefig` (overlay, heatmap + colorbar), a DPG frame buffer, the Gradio displayed image, the demo snapshot and the docs sweep.

### Decisions

- **Fractions in [0, 1]**, `(0, 0)` = top-left. Pixel helper: **`interactive_pipe.to_pixels(value, img)`** (also exported from `headless/pointer.py`, next to the controls): the filter receives a plain tuple, so a function is the one-liner; it lives with the controls rather than in `draw` because it converts coordinates and draws nothing (and `draw.py` is not in this plan's files). Point → `(col, row)` clipped into the image; region → `(x0, y0, x1, y1)` such that `img[y0:y1, x0:x1]` is never empty. `img` may be an array, an `Image` or a shape. `to_fractions` is the inverse (not exported at top level).
- **Validation**: wrong length, non-number, NaN or a coordinate outside [0, 1] **raise** (`ValueError` / `TypeError`, naming the control), for defaults, `pipe(img, seed=...)`, tuning files and literal kwargs alike (float noise ≤ 1e-6 is snapped). A **region given the other way round is reordered**, not rejected: a drag from bottom-right to top-left produces exactly that. The fallback sliders clamp like any slider; dragging `x0` past `x1` pushes `x1`.
- **`on=`**: any variable produced by the pipeline (or an input) is accepted, since `layout.grid` may show it; the error lists the displayed outputs. Default: the first image cell of the current frame. A text / curve / table cell takes no gesture; a matplotlib figure target logs one warning and is ignored (in Qt threaded mode figures are rasterised in the worker, so there clicks map to raster pixels).
- **Gestures**: press-release within 3 screen pixels = click → sets the point nearest to the click among the points of that cell (several points per image work); a longer plain drag pans (Qt, DPG) or does nothing (mpl); shift at press time = region: the nearest region of that cell is redrawn live while dragging, without panning.
- **Fallback is the default**: `InteractivePipeGUI.pointer_gestures` is `False` on the base class; a backend opts in with `True` or a tuple of kinds (`("point",)` for Gradio). `controls_for_backend` swaps the control for its sliders (`seed x`, `seed y`, `roi x0`…`roi y1`, which read/write the parent control: no duplicated state) in the control list and in its panel, and swaps back for a gesture backend built later.
- **Overlay**: drawn by the window only (Qt `paintEvent`, DPG drawlist items, mpl artists, Gradio on the displayed uint8 copy); outputs, snapshots and sweeps are untouched. Regions under points, magenta cross / cyan rectangle with a dark outline and the control name.

### Not done / limits

- `on=` is validated when a GUI is built and in `describe()`, **not when a `HeadlessPipeline` is built**: `headless/pipeline.py` / `core/` are not in this plan's files (see "Left for review").
- Gradio: no region gesture (sliders), as allowed by the plan. Notebook: sliders only (no events without `ipympl`).
- Clicks on matplotlib figure outputs (data coordinates of the axes) are not supported.
- `docs/guide/examples.md` (demo gallery table) not updated: not in this plan's files. Suggested row: ``| `pointer_demo.py` | Mouse input: a clicked point and a dragged region ([mouse input](mouse-input.md)) |``.

### Left for review

- **Build-time `on=` check** (`headless/pipeline.py`, not mine). Reproducer:
  ```python
  @interactive(where=PointControl((0.5, 0.5), on="missing"))
  def misplaced(img, where=(0.5, 0.5)):
      return img


  def bad(img):
      out = misplaced(img)
      return [img, out]


  HeadlessPipeline.from_function(bad, inputs=["img"]).run()  # no error; GUI build / describe() raise
  ```
  Suggested fix: at the end of `HeadlessPipeline.from_function`, after `data_class.controls = control_list`, call `interactive_pipe.headless.pointer.check_targets(data_class)` (it raises `ValueError` with the available outputs). `snapshot` / `sweep` would then fail early too.
- Small edits outside the literal file list, all in `graphical/`: the base class `graphical/gui.py` (`pointer_gestures` attribute, `check_targets` + `controls_for_backend` in `__init__`, gesture lines in `show_help`) — needed so the fallback is what any backend gets by default; `graphical/pointer_input.py` is new.
- `ruff format .` also reformats python code blocks inside markdown plan files (it added a blank line in this plan's example block).

### Lines for the packaged skill (to merge later)

```markdown
### Mouse input: a point or a region on an image
| Need | Declaration (values are fractions of the image size, (0, 0) = top-left) |
|---|---|
| Clicked point | `seed=PointControl((0.5, 0.5), on="img")` → `(x, y)` |
| Dragged region (shift + drag) | `roi=RegionControl((0.25, 0.25, 0.75, 0.75), on="img")` → `(x0, y0, x1, y1)` |
- In the filter: `col, row = to_pixels(seed, img)`; `x0, y0, x1, y1 = to_pixels(roi, img)` then `img[y0:y1, x0:x1]` (never empty).
- `on=` names the displayed output that receives the gesture (default: the first image); an unknown name raises when the GUI is built.
- Headless it is a plain parameter: `pipe(img, seed=(0.2, 0.4))`, `sweep(..., seed=[(0.1, 0.1), (0.6, 0.4)])`; `describe()` kind `"point"` / `"region"`.
- Qt / DPG / mpl: click and shift-drag, the window draws the marker; Gradio: click (regions are sliders); notebook: sliders. Snapshots do not show the marker: draw it with `interactive_pipe.draw` if it must be in the output.
```
