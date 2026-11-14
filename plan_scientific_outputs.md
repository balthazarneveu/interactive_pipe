# Plan: scientific output types — figures, heatmaps with colorbars, overlays

Branch: `feature/scientific-outputs`, cut from `integration/next-level`.

## Why

The library displays numpy images, `Curve`, `Table` and strings. For
scientific and engineering debugging people also need: any matplotlib figure
they already know how to make, a heatmap with a readable scale, and marks
drawn on top of an image (detections, keypoints, regions, labels). Each of
these should be one line in a filter and behave the same on every backend
and in `pipeline.snapshot(...)`.

## Environment — read this first

This is a git worktree at `/home/bneveu/code/interactive_pipe_outputs`. It has **no `venv/`**; the shared venv's
editable install points at another checkout. Replace `CLAUDE.md`'s
`./venv/bin/python` commands by:

```bash
cd /home/bneveu/code/interactive_pipe_outputs
export PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg
PY=/home/bneveu/code/interactive_pipe/venv/bin/python
$PY -c "import interactive_pipe; print(interactive_pipe.__file__)"   # must print a path inside THIS worktree
$PY -m pytest test/ -q --tb=short        # baseline on this base: 867 passed, 6 skipped
$PY -m ruff format . && $PY -m ruff check --fix .
```

Check the printed path before trusting any test result. Do not `pip install`
into the shared venv. Do not read, edit or run git commands in any other
checkout (`/home/bneveu/code/interactive_pipe`, `..._snapshot`,
`..._integration`, and the sibling worktrees of the other agents).

## Context

Base branch `integration/next-level` already contains two pieces of work done
tonight; read their plans' Status sections first, they describe the code you
build on: `plan_fix_silent_failures.md` (strict pipeline parser,
`PipelineSyntaxError`, call validation, control renaming, `save`,
`layout.style` colormap) and `plan_agent_snapshot_loop.md`
(`snapshot` / `sweep` / `describe` on pipelines and single filters,
`INTERACTIVE_PIPE_SNAPSHOT`).

Two other agents work in parallel on sibling branches:
- `feature/declare-less` owns `helper/keyword_args_analyzer.py`,
  `helper/control_abbreviation.py`, `helper/filter_decorator.py`,
  `headless/control.py`, `core/engine.py`, `core/filter.py`,
  `headless/explore.py`.
- `feature/agent-packaging` owns `pyproject.toml`, `cli.py`, a new
  `__main__.py`, and the bulk rewrite of
  `.claude/skills/build-interactive-pipeline/SKILL.md` and the docs index.
You own `graphical/window.py`, the backend files under `graphical/`,
`headless/snapshot.py`, `data_objects/` and `core/context.py`.
Stay out of the files they own. Keep edits to shared files (`CHANGELOG.md`,
`CLAUDE.md`, `SKILL.md`, `__init__.py`, `mkdocs.yml`, `readme.md`) to small
additive hunks in your own section, so the three branches merge cleanly.

## Ground rules

- Follow `CLAUDE.md` otherwise: ruff format + check and the full suite before
  every commit, small focused commits bundled with their tests, exceptions
  not `assert`, no mutable defaults.
- Work only on this branch in this worktree. Do not push, open a PR, merge,
  bump the version, publish, or comment on GitHub.
- Never open a real window (`QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg`).
- **Hard stop: 11:30 CET on 2026-11-14.** Check `date` regularly. By 11:15
  stop starting new work, leave the tree clean and the suite green, and fill
  in the Status section.
- Nobody can answer questions. When a decision here proves wrong once you
  read the code, pick the option that keeps existing user code working and
  record it in Status.
- Backward compatibility: every pipeline in `demo/`, `samples/`, docs code
  blocks and `test/` must keep working unchanged.
- Each item needs tests in new test files. Items are ordered by value and
  each is shippable alone.
- When you produce anything visual, render it with `pipeline.snapshot(...)`
  and look at the PNG with the Read tool before calling it done.

## Work items

### 1. Snapshot honours `layout.style(colormap=..., vmin=..., vmax=...)`

The colormap support added tonight lives in the GUI path
(`graphical/window.py`, `core/context.py`); `headless/snapshot.py` was written
on another branch and ignores it, so a heatmap that is coloured in the GUI is
grey in the snapshot. Make both go through the same code, and add a test that
a snapshot of a styled 2D array is not grey.

### 2. Colorbar and value readout for heatmaps

- `layout.style(name, colormap=..., colorbar=True)` shows the scale. Find the
  cheapest design that works on **every** backend and in the snapshot: since
  heatmaps are converted to RGB in one shared place, rendering the bar (with
  min / max / a few tick labels, optional `unit="dB"`) into the image itself
  is the uniform option; a native colorbar only on some backends is not
  acceptable. Text must stay legible on small arrays (a 32x32 map upscaled).
- Diverging data: `layout.style(..., colormap="RdBu", center=0)` makes the
  range symmetric around the centre.
- Document how NaN and masked values are shown and make it deliberate.
- The Qt viewer has a pixel readout: check what it reports for a heatmap
  (the colour triplet is useless; the original scalar is what is wanted) and
  fix it if that is a contained change. Otherwise note it in Status.

### 3. matplotlib figures as an output type

A filter may return a `matplotlib.figure.Figure` (and, as a convenience, an
`Axes`, meaning its figure).

- Must work on every backend (qt, dpg, mpl, nb, gradio), in `snapshot` /
  `sweep`, in `save()` and in `export_animation`. The uniform way is to
  rasterise the figure with Agg in one shared place and hand the backends an
  image; do that unless a backend has a clearly better native path that is
  cheap (gradio and nb can take a figure directly).
- Do not leak figures: a slider drag creates one figure per run. Figures made
  with `pyplot` stay registered in pyplot's global state until closed —
  close them after rasterising, and document that
  `matplotlib.figure.Figure()` (no pyplot) is the recommended way to build
  them in a filter. Test that 200 runs do not grow `plt.get_fignums()`.
- Resolution: pick a dpi that gives a sharp result in a typical cell; let
  `layout.style(name, dpi=...)` override it.
- `display_kind` gets a new kind; check every place that switches on kinds
  (grep `display_kind` and the `isinstance(..., Curve)` chains in each
  backend), including the cell-rebuild logic when a filter changes output
  type between runs.
- Demo: `demo/matplotlib_figure_demo.py` — something a `Curve` cannot do
  (a quiver or contour plot, or a polar plot) driven by two sliders.

### 4. Drawing on images

A small, dependency-free drawing module (numpy + Pillow, both core
dependencies; do not require OpenCV), exported as `interactive_pipe.draw`
(check the name does not collide with anything):

- `draw.points(img, xy, color=..., radius=..., labels=None)`
- `draw.boxes(img, boxes, labels=None, color=..., width=...)`
  (state the box convention — `(x0, y0, x1, y1)` in pixels — and offer
  `fmt="xywh"`)
- `draw.lines(img, segments or polyline, ...)`, `draw.polygon(...)`
- `draw.text(img, text, xy, ...)` with a readable default (outline or
  background box), anchor option
- `draw.mask(img, mask, color=..., alpha=...)` — blend a boolean or label
  mask; a label mask gets one colour per label
- `draw.side_by_side(a, b, ...)` / `draw.grid([...])` only if they are not
  already covered by the output layout — probably skip.

Rules: pure functions returning a new array (inputs are read-only views in a
pipeline); accept float `[0, 1]` and `uint8`, grayscale and RGB, and return
the same dtype and range as the input (grayscale is promoted to RGB when a
colour is drawn); coordinates in pixels, `(x, y)` order, sub-pixel values
accepted; out-of-image marks are clipped, not an error; colours as names,
`(r, g, b)` floats or hex; a default colour cycle for per-item colours.
Vectorise the conversions — these run on every slider move; time a
1920x1080 image with 200 boxes and report it in Status.

Demo: `demo/overlay_demo.py` (synthetic blobs, a threshold slider, detected
centroids and boxes drawn on the image, a count in the title).

### 5. `Image` data object as an output (if cheap)

`interactive_pipe.Image` exists and is exported but is not a displayable
output (`display_kind` returns None for it). Either make it one
(its array, its `title` as the cell title) on every backend and in the
snapshot, or record why not. Small item — do not let it grow.

### 6. Docs

- New guide page `docs/guide/figures-and-overlays.md` in the `mkdocs.yml`
  nav, with images generated by `pipeline.snapshot` from your demos and
  committed under `docs/images/`.
- Update the "what can a filter return" statements wherever they exist
  (grep the docs and `SKILL.md` for "Curve" / "Table" lists) with small
  additive edits, and the backend feature matrix in
  `docs/getting-started/backends.md`.
- `CHANGELOG.md` "Unreleased": your own bullets.

## Out of scope

Mouse input (clicking a pixel, dragging a region) is a separate piece of
work. Do not start it. If you finish everything above with time to spare,
write a short design note for it at the end of Status instead: which backends
can report clicks in image coordinates today (the Qt and DPG viewers already
map the cursor to pixels for zoom and readout), what the user-facing
declaration could look like, and how it would behave headless and in
`snapshot`.

## Status

Agent run of 2026-11-14, started 02:02 CET, autonomous (nobody reachable
before 11:30). Environment checked: the shared interpreter imports
`interactive_pipe` from this worktree's `src/`; baseline `867 passed,
6 skipped` reproduced before any change.

### 1. Snapshot honours `layout.style` heatmap options — done

- New module `graphical/display.py` (no GUI toolkit import): `display_kind`,
  `apply_display_style` and the new single entry point
  `prepare_display(content, style)`. `graphical/window.py` re-exports the old
  names, so existing imports keep working.
- Users of `prepare_display`: `InteractivePipeWindow._styled` (Qt, DPG, mpl,
  nb), `headless/snapshot.result_grid` (snapshot and sweep) and — found on
  the way — the Gradio refresh path: `MainWindow.process_outputs` and the
  dry-run container detection bypassed `refresh_display`, so a colormap was
  shown on the first frame only, never after a slider move. Both now go
  through `_styled`.
- Tests: `test/test_display_shared_style.py` (snapshot of a styled 2D array is
  not gray, snapshot cell == GUI conversion, result left raw, Gradio refresh).


### 2. Colorbar, diverging range, NaN policy, readout — done

- `layout.style(name, colorbar=True, unit="dB")`: the scale is drawn **into
  the image** by `graphical/display.py` (Pillow + matplotlib's bundled
  DejaVu Sans, `MaxNLocator` round ticks, both ends always labelled, interior
  ticks skipped when they would overlap), so it is identical on every backend
  and in snapshots. A map shorter than 256 px is first upscaled by an integer
  factor (nearest, at most x32) so the labels are drawn >= 12 px tall; font
  height is 5 % of the map height, 12-48 px. Strips are `lru_cache`d per
  (colormap name, range, height, unit). `colorbar=True` without a colormap
  uses `gray`.
- `center=c` widens `[vmin, vmax]` (explicit or automatic) to be symmetric
  around `c`.
- NaN / masked policy (decision): NaN and `numpy.ma` masked pixels are drawn
  in magenta `BAD_COLOR = (1, 0, 1)` — a colour no common colormap uses, so a
  missing value never reads as a valid one — and are ignored by the automatic
  range; `±inf` are clipped to the ends of the scale. A `Colormap` object with
  its own `set_bad` colour (alpha > 0) wins. Without a colormap, a styled
  array containing NaN is promoted to RGB to show them (without NaN it stays
  a 2D windowed array, as before). Unstyled arrays are untouched.
- `vmin` / `vmax` / `center` must be numbers (`TypeError` from
  `layout.style`, surfaced as a `FilterError`). New keys added to
  `SUPPORTED_STYLE_KEYS`; the existing unknown-key test used `colorbar` as
  its example of an unknown key — switched to `colourbar`.
- Qt readout: it already reported the raw scalar for a colormapped heatmap
  (it keeps the raw outputs). With a colorbar the displayed image is
  upscaled and wider, so it fell back to the RGB triplet: `ImageView` got an
  optional `readout=(upscale, h, w)` mapping display pixels back to data
  pixels (coordinates and value in data space, nothing over the colorbar),
  set by `qt_gui.update_image` from `display.heatmap_geometry`. The DPG
  viewer has no value readout today (zoom only), nothing to fix there.
- Tests: `test/test_heatmap_colorbar.py`.

### 3. matplotlib figures as an output type — done

- A filter may return a `Figure`, an `Axes` (its figure) or a `SubFigure`
  (its root figure). `display_kind` reports `"figure"`; `prepare_display`
  rasterises it with Agg (`display.rasterize_figure`) into an `(H, W, 3)`
  float32 image, so every backend (qt, dpg, mpl, nb, gradio), `snapshot`,
  `sweep` and `export_animation` receive an ordinary image. Decision: no
  native gradio (`gr.Plot`) / notebook path — the uniform raster is what
  makes snapshots match the GUI, and it needs no per-backend code.
- Kind switches: since the conversion happens before `update_image`, each
  backend sees kind `"image"` and its existing rebuild logic applies; tested
  figure <-> image / curve / table / text switches on Qt, DPG and mpl. No
  backend `isinstance` chain needed a new branch.
- Leaks: before rasterising, a figure registered in pyplot is closed
  (`release_pyplot_figure`; the Figure object stays usable). 200 GUI
  refreshes of a filter calling `plt.subplots()` leave `plt.get_fignums()`
  unchanged; snapshot / sweep / save release too. A plain headless call
  `pipe(img)` returns the figure to the caller and does not close it (by
  design). Docs recommend `matplotlib.figure.Figure()`.
- Resolution: `FIGURE_DPI = 120` (a default 6.4 x 4.8 in figure gives
  768 x 576 px, shrunk rather than blown up in a typical cell);
  `layout.style(name, dpi=...)` overrides it (new supported key, validated
  as a number). The user figure's own dpi is restored after drawing.
- The raster is cached on the figure and reused while `fig.stale` is False,
  so a cached filter output is not redrawn on every refresh.
- Transparent figures are composited on white.
- `save()`: figures are written with `savefig` (`.png` by default; `.pdf`,
  `.svg`, `.jpg` suffixes kept). `export_animation`: every output now goes
  through `prepare_display` with its style before frame conversion, so
  figures animate and styled heatmaps are exported in colour (before: raw
  2D array as gray) — a deliberate behaviour change, matching the GUI.
- Demo: `demo/matplotlib_figure_demo.py` (two charges, sliders `separation`
  and `charge_ratio`; a contour + quiver Figure next to the potential as a
  `RdBu_r` heatmap with `center=0` and a colorbar). Checked with
  `INTERACTIVE_PIPE_SNAPSHOT`.
- Tests: `test/test_figure_outputs.py`.

### 4. Drawing on images — done

- `src/interactive_pipe/draw.py`, exported as `interactive_pipe.draw`
  (`from interactive_pipe import draw`, `ip.draw.boxes(...)`; also in
  `__all__`). The name was free: no `draw` attribute, module or user of
  that name in `src/`, `test/`, `demo/`, `samples/`, `docs/`.
- Functions: `points` (discs / circles, labels), `boxes` (`(x0, y0, x1,
  y1)` pixels by default, `fmt="xywh"`, labels on a filled tag above the
  box, inside it when the box touches the top), `lines` (one polyline
  `(M, 2)`, `(K, M, 2)` — `(K, 2, 2)` = segments — or a ragged list,
  `closed=`), `polygon` (outline and/or translucent `fill_alpha`), `text`
  (white with a black outline by default; `background=` box instead;
  anchors by name `"top-left"` ... `"bottom-right"` or Pillow anchors;
  multi-line; lists of texts), `mask` (bool -> one colour; int labels -> one
  colour per label, 0 = background, cycled; float -> soft opacity), plus
  `to_rgb` and `DEFAULT_COLORS` (tab10). `side_by_side` / `grid` skipped as
  the plan suggested: the output layout already does that.
- Rules implemented as specified: pure (copies, read-only inputs fine),
  dtype and range kept (float, `uint8`, also `uint16`), gray promoted to RGB,
  RGBA kept (marked pixels become opaque), `(x, y)` pixels with sub-pixel
  values, out-of-image clipped, NaN items skipped, colours as names / hex /
  float tuples / 0-255 tuples, per-item lists, default cycle.
- Implementation: `uint8` gray/RGB images are drawn on directly by Pillow
  (fast path); float / `uint16` / RGBA images get a transparent RGBA overlay
  blended into a copy on the marked pixels only (the other pixels keep their
  exact float values). The overlay is kept premultiplied, which is how
  Pillow writes antialiased text onto transparent pixels — found while
  testing: without it, text edges on float images were darkened twice.
  Label tags (text on a filled box) are rendered once and `lru_cache`d, since
  the same labels come back on every slider move. Text uses matplotlib's
  bundled DejaVu Sans (`display.get_font`).
- Timing, 1920x1080 RGB, 200 random boxes (machine shared with two other
  agents, load average ~20 on 8 cores, so these are pessimistic; min of 7
  runs after one warm-up): `uint8` 21 ms, 47 ms with 200 labels; `float32`
  39 ms, 156 ms with 200 labels (the float cost is the gather/blend/scatter
  of the ~750k marked pixels — labels are filled tags). First call with new
  labels pays the text rendering (~1 ms per label).
- Demo: `demo/overlay_demo.py` — synthetic blobs, `threshold` / `min_area`
  sliders (plus `blobs`, `noise`), connected regions by numpy label
  propagation (no scipy), boxes + centroids + labels, the count in the
  title and in the image, and the label mask with `draw.mask`. Checked with
  `INTERACTIVE_PIPE_SNAPSHOT`.
- Tests: `test/test_draw.py`.

### 5. `Image` data object as an output — done

- `prepare_display` shows an `Image` as its array (with the output's
  `layout.style` applied: an `Image` of a 2D array can be a heatmap);
  `display_kind(Image)` is the kind of its array. Every backend, the snapshot
  and `export_animation` get it through the shared conversion; `save()`
  already handled `Image`. The Qt pixel readout reports the `Image`'s float
  values (raw output unwrapped).
- Title rule (decision): `layout.style(title=...)` wins, else
  `Image.title`, else the output name. (A `Curve`'s own title keeps winning
  over the style, as before: not changed.) Implemented once in
  `InteractivePipeWindow.resolve_style` (also used by Qt's worker-thread
  layout copy) and in `snapshot.output_title`.
- Behaviour change on the way: a `layout.style` call without `title` (e.g.
  only `colormap=`) used to blank the cell title on Qt / DPG / Gradio /
  mpl; it now falls back to the output name like an unstyled output (the
  snapshot already did). `title=""` still hides the title, now also in the
  snapshot (it used to show the name there).
- Tests: `test/test_image_output.py` (window, snapshot, Qt, DPG, mpl, Gradio).

### 6. Docs — done

- New guide page `docs/guide/figures-and-overlays.md` (nav: Guide >
  Displaying results > "Figures, heatmaps & overlays"): figures, heatmap
  keys and NaN policy, the `draw` API and conventions, `Image` outputs, and
  a "what a filter can return" table. Its four code blocks were extracted
  and executed (polar figure, heatmap, `draw` filter via `detect.snapshot`,
  `Image`); the heatmap image is produced by the page's own block.
- Images (all from `snapshot`, looked at): `docs/images/figures_heatmap_colorbar.png`,
  `figures_matplotlib_demo.png` and `figures_overlay_demo.png` (the two
  demos run unmodified with `INTERACTIVE_PIPE_SNAPSHOT`).
- Small additive edits: `docs/guide/layout.md` (style table rows), backend
  matrix in `docs/getting-started/backends.md` (3 rows), quickstart `save`
  sentence, `docs/guide/curves.md` pointer, `docs/guide/examples.md` demo
  table, `mkdocs.yml` nav, `CHANGELOG.md` (own "Scientific outputs"
  subsection at the end of Unreleased), `SKILL.md` (own section before the
  snapshot loop), `CLAUDE.md` (short "Scientific outputs" section pointing
  to `prepare_display` as the single place for new output types).
- Not touched (owned by `feature/agent-packaging`): `docs/index.md`,
  `readme.md` feature list, the skill's demo count.
- Not run: the mkdocs build (mkdocs is not installed in the shared venv).
