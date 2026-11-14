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

(to fill)
