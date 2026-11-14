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

In progress (agent run of 2026-11-14, started 04:06 CET). Baseline: 1444 passed, 6 skipped.

- Item 1 done: `53e3a0c`.
- Item 2 done: `def0a61`.
- Item 3 done: `bbb1910`.
- Item 4 done: `9d09123`.
