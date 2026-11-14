# Plan: display polish found by the dogfooding round

Branch `feature/display-polish`, based on `integration/next-level`. Read the friction log in the Status of `plan_agent_dogfood.md` first (items 6, 7, 8, 9) and the "Left for review" of `plan_robust_display.md`. Every item here is visual: render before and after (snapshot PNG and an offscreen Qt grab), read both, and keep a before / after pair for the three most visible ones under `docs/images/` only if a docs page uses it.

## Items

1. **"Nothing found" must not crash** (log item 6): `draw.boxes(img, np.zeros((0, 4)), color=[])` and every other `draw.*` function with zero marks returns the image unchanged; an empty `Table` displays as an empty table with its headers in snapshots and on every backend (check Qt, DPG, mpl, Gradio); `Table` accepts numpy columns, pandas frames if pandas is present, list of dicts, dict of lists. Parametrised test over all `draw` functions × empty inputs and over the table inputs.
2. **Colorbar** (log item 8): the unit must not be repeated on every tick — put it once (top of the bar or as a short label); add `label=` if a longer text is wanted; ticks formatted consistently (same number of decimals for all labels of a bar); the end labels must not overlap the nearest round tick (drop the round tick, never the end). Check with ranges like [1.0, 4.2], [-0.39, 0.39], [0, 255], [1e-4, 3e-3], constant maps, and tiny (16 px high) and large maps.
3. **Figure text size** (log item 9): a `Figure` output is rasterised at its `figsize` then scaled to the cell, so its text size depends on `figsize` and differs from the `Curve` next to it. Make the default consistent: the text of a figure and of a `Curve` in neighbouring cells should come out the same size in a snapshot and in the Qt window for the default `figsize`; document how `figsize` / `dpi` act. If rasterising at the cell size is feasible on Qt / DPG (re-rasterise on resize, debounced), do it; otherwise choose a sensible constant and explain.
4. **Metric readouts** (log item 7): `layout.style(name, subtitle=...)` exists since the first round; check it on every backend and in snapshots, then make the common case one line: a filter should be able to attach a short readout to an output without wrapping it in `Image(...)` — verify whether `layout.style("out", title=f"PSNR {psnr:.2f} dB")` already does it everywhere including snapshot and sweep cells (sweep cells must show each cell's own title), fix what does not. `str` outputs: bigger, wrapped text in a cell (also on mpl: `mpl_window.py` does not wrap, the display agent pre-wrapped errors at 36 characters as a workaround — do it properly).
5. **Slider value text in Qt**: values show as `6.000e+00`, `1.000e-01`. Show them like a person would write them (`6`, `0.1`, `0.005`, `1e-05` only when needed), consistently on Qt, DPG, mpl, Gradio, notebook and in the snapshot caption. A sibling agent is adding log-scale sliders and nicer default steps in `graphical/*_control.py` at the same time: keep your change to one shared formatting function (put it next to `prepare_display` or in a small new module) plus the one-line call in each backend, to keep the merge trivial.
6. **Messages in `gradio_control.py` / `nb_control.py`** that name no control (`Expected int control type, got <class 'float'>`): name it. Same caveat as item 5: minimal edits.
7. Flaky `test/test_command_line.py::test_doctor_opens_no_window` (a `QApplication` left alive by an earlier test): find which test leaks it and fix the leak or the test's assumption.
8. If time remains: clicks on matplotlib figure outputs for `PointControl` (data coordinates of the axes) — only if it fits cleanly, otherwise leave it.

## Ownership

Yours: `src/interactive_pipe/graphical/display.py`, `graphical/window.py`, image / viewer / window files of each backend (`qt_image.py`, `qt_viewer.py`, `dpg_image.py`, `dpg_viewer.py`, `mpl_window.py`, `gradio_outputs.py`), `headless/snapshot.py`, `data_objects/`, `draw.py`, `docs/guide/figures-and-overlays.md`, `docs/guide/tables.md` / layout pages where needed.
Not yours: `core/`, `headless/` other than `snapshot.py`, `helper/`, the panel builders and `graphical/*_control.py` beyond the one-line calls of items 5 and 6 (a control-semantics agent is changing them); `agent/`, the skill, `demo/gallery/` (put what the gallery or skill should change in Status).

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

**Summary (04:56 CET):** items 1–7 done on `feature/display-polish`
(`53e3a0c`..HEAD; nothing pushed, no PR, no merge, no version bump); item 8
left (does not fit cleanly, see below). Final state: `1724 passed, 12 skipped`
(baseline `1444 passed, 6 skipped`), ruff format / check clean, pyright clean
in every file this round changed except errors that were already there
(pointer-input code: `pointer_input.py` 25, `headless/pointer.py` 4,
`dpg_image.py` 6 in `draw_overlay`, `dpg_gui.py:717`, `qt_gui.py:905`; plus the
known `qt_control.py` 7 and `dpg_panels.py` 1).

Agent run of 2026-11-14, started 04:06 CET, autonomous. Every visual change
was rendered (snapshot PNG, offscreen Qt grab, mpl Agg savefig) and looked at
before and after; the before / after PNGs stayed in the session scratchpad.
Only docs images a page already uses were regenerated (after only):
`docs/images/figures_heatmap_colorbar.png`, `docs/images/figures_matplotlib_demo.png`.

| Item | Commit | Tests |
|---|---|---|
| 1. "Nothing found" | `53e3a0c` | `test/test_nothing_found.py` (160 cases) |
| 2. Colorbar | `def0a61` | `test/test_heatmap_colorbar.py` (rewritten label tests) |
| 3. Figure text size | `bbb1910` | `test/test_figure_text_size.py`, `test_figure_outputs.py` |
| 4. Readouts | `9d09123` | `test/test_readouts.py` |
| 5. Slider value text | `e5593f7` | `test/test_value_format.py` |
| 6. Control messages | `06803be` | `test/test_control_error_names.py` |
| 7. Flaky doctor test | `9f5acab` | `test/test_command_line.py` |
| pyright on changed files | `856074e` | |

### 1. "Nothing found" — done (`53e3a0c`)

- Every `draw` function accepts zero marks with any `color` (`None`, `[]`,
  an empty array, a name) and returns the image values unchanged. A gray
  image still comes back RGB-promoted (same shape with and without marks, so
  the display does not jump between frames — the documented convention).
  `color=[]` with marks is still an error, now naming the count.
- `Table`: dict columns may be lists, tuples, 1D numpy arrays or pandas
  `Series` (numpy scalars become `int` / `float`, so `precision` applies);
  errors name the column. Pandas frames, list of dicts as before.
- Empty table: one renderer for snapshots and the Qt / mpl windows
  (`data_objects/table.py::draw_table`, moved from `snapshot.py`): header row
  plus "(no rows)"; "(empty table)" without columns. It also fixed two
  pre-existing problems seen on the way: on Qt the rows of every table were
  squeezed (row height computed for the initial 10 x 10 in canvas; now read at
  each draw) and the title was cut on the mpl backend (now inside the axes).
  DPG shows the header row (native table). Gradio showed the column names as a
  first data row under "1", "2" headers: now `{"headers", "data"}`.

### 2. Colorbar — done (`def0a61`)

- `unit` written once above the bar; very large / small ranges (>= 1e5,
  < 1e-2) put one `×10ⁿ` multiplier there instead of `1e-03` on each tick.
- Longer text: `colorbar="log10 |F|"` (a string instead of `True`) writes it
  vertically along the bar. I did not add `label=`: `layout.style` keys are
  checked in `core/context.py` (not mine) and an unknown key warns; the
  display also reads `style["label"]` if it is ever registered (see Left for
  review).
- Same decimals for every label of a bar; ends always labelled with enough
  decimals to be within 0.5 % of the true value (`4.2`, `-0.39`); round ticks
  1/2/5·10^k, a tick too close to an end is dropped (never the end). Checked
  on [1, 4.2], [-0.39, 0.39], [0, 255], [1e-4, 3e-3], [0, 1e6], [-3.7, 12.3],
  constant maps, 16 px to 1200 px maps.

### 3. Figure text size — done (`bbb1910`)

Rasterising at the cell size was feasible: a figure output is now drawn at the
largest size of its own aspect ratio fitting its cell, at 100 px per inch (the
dpi of the Qt curve canvas), so its text is the size of a `Curve`'s next to it
whatever its `figsize` (`rasterize_figure(box=, pixel_ratio=)`).

- Snapshots / sweeps: drawn again at the pixel size of their axes once the
  layout is known (2x oversampled, smoothly reduced); the auto dpi ignores
  figure rasters; snapshot curves now use matplotlib's default tick size (was
  8 pt) like the GUI curves.
- Qt: at the view size, again 150 ms after the last resize event (debounced
  `QTimer` in `ImageView`), threaded runs included (the worker rasterises at
  the last known size; a resize re-rasterises under the run lock).
- mpl and notebook windows: at the axes size, again on `resize_event`.
- DPG: at the natural size of a plot cell (480 x 320), then laid out like a
  plot (DPG plots use DPG's own font, ~13 px, vs 10 pt at 100 dpi ≈ 14 px).
- Gradio and `export_animation` keep the `figsize` at 120 dpi (no cell size).
- A shrunk figure keeps its text size in points, so with matplotlib's default
  margins its xlabel was cut: such figures are drawn with `tight_layout`
  (default margins only; `subplots_adjust` / constrained layout kept; the
  figure is restored afterwards).
- Docs: `figures-and-overlays.md` explains what `figsize` and `dpi` do now.

### 4. Readouts — done (`9d09123`)

- `layout.style(name, title=f"PSNR {psnr:.2f} dB")` (and `subtitle=`) already
  followed each frame on Qt, DPG, mpl, in snapshots and in each sweep cell
  (each cell its own title). Gradio did not: labels were set once at build;
  now the component label is updated (`gr.update(value=, label=)`) whenever
  the title differs from the one shown. Documented in `layout.md` ("Metric
  readouts") as the one-line way, no `Image(...)` wrapper needed.
- `str` outputs: 12 pt and wrapped to the cell on every backend
  (`display.wrap_text` for snapshots and the mpl / notebook windows,
  word-wrapped `QLabel` on Qt, a larger DejaVu font on DPG). The 36-character
  pre-wrap of display errors in `window._styled` is gone (each backend wraps).

### 5. Slider value text — done (`e5593f7`)

New module `graphical/value_format.py` (`format_number`: 4 significant
digits, positional in [1e-4, 1e6): `6`, `0.1`, `0.005`, `20000`, `1e-05`),
with `printf_format` (same text, for DPG's native slider format),
`JS_FORMAT_NUMBER` (Gradio range slider readout) and `D3_FORMAT` (ipywidgets).
One call per backend: Qt value label, DPG slider (create / change / reset),
mpl `Slider` text, notebook `readout_format`, Gradio range readout, snapshot
caption. Gradio's native sliders show the number as is (already `6`, `0.1`).
The notebook format is `.6` (ipywidgets refuses d3's `~` flag): 6 significant
digits, so 1/3 shows `0.333333` there.

### 6. Control messages — done (`06803be`)

`graphical/control_errors.py`: `BaseControl.__init_subclass__` in
`gradio_control.py` and `nb_control.py` (one 3-line hook per file, no message
edited) wraps `check_control_type` / `create` of every factory class:
`control 'gain' (filter 'amplify'): Expected int control type, got <class 'float'>`.

### 7. Flaky `test_doctor_opens_no_window` — done (`9f5acab`)

The first test creating the process-wide `QApplication` in collection order is
`test_annotation_controls.py::test_qt_dropdown_drives_enum_parameter` (any Qt
GUI test does: `InteractivePipeQT` creates it); whether it is still alive 170
tests later depends on garbage collection, so the test's assumption ("no
QApplication in this process") was wrong, not the doctor. The check now runs
`diagnose()` in a fresh interpreter, plus an in-process test that `diagnose()`
leaves `QApplication.instance()` as it found it. Reproduced before the fix: the
full suite failed it deterministically at test 183 with `-x`.

### 8. Clicks on figure outputs — not done

It does not fit cleanly in this round: `PointerTargets` (`pointer_input.py`)
rejects figure cells on purpose, a `PointControl` value is a fraction of an
image, and the backends' gesture code maps clicks through the image data size.
Doing it needs (a) `rasterize_figure` to record each axes' pixel box in the
raster it returns (the boxes change with the cell size now), (b) a value
convention for figures — fractions of the clicked axes' data area, or data
coordinates via the axes' `transData.inverted()` stored with the raster —
in `headless/pointer.py`, and (c) `data_size` / overlay mapping per backend.
None of these files are mine.

### Left for review (files not mine)

- `core/context.py`: register `"label"` in `SUPPORTED_STYLE_KEYS` if a
  `layout.style(..., label=...)` colorbar label is wanted (the display already
  reads it; today `colorbar="text"` does it without a warning). Docstrings
  there are now outdated: `unit` "appended to the colorbar labels" (now written
  once above the bar) and `dpi` "default 120" (now: pixels per inch, 100 in a
  cell, see `figures-and-overlays.md`).
- Skill (`src/interactive_pipe/agent/build-interactive-pipeline/SKILL.md`,
  line ~142): "`unit="px"` is printed on every tick, so put a long unit in
  `title=`" and "a smaller `figsize` gives larger text" are no longer true;
  it can say: empty `Table` / `draw.*(..., color=[])` are fine, `Table` takes
  numpy columns, `colorbar="label"`, readouts with
  `layout.style(title=f"...")`, figure text = curve text.
- Gallery (`demo/gallery/`): `blob_detection.py` workarounds can go
  (`color=[...] or None`, `"no detection"` string, `.tolist()`); the
  `figsize` tuned by trial and error in `optimizer_trace` / `pid_control` no
  longer matters; `frequency_filtering` can use `unit=` again; regenerate
  `docs/images/gallery/*.png` with `scripts/make_gallery.py` (figure cells
  now render at cell size, colorbars changed).
- `headless/animation.py` calls `prepare_display` without a cell size:
  figures in an exported animation keep their `figsize` (fine, documented).
- `ruff format .` rewrites `plan_agent_dogfood.md` (markdown formatting):
  reverted before each commit of this round; worth excluding `*.md` plans in
  the ruff config.
