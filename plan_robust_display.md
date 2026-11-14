# Plan: tolerant display, quiet errors, clean process state, docs build

Branch `feature/robust-display`, based on `integration/next-level`. This is the consolidation round: the items below were found while reviewing the merged result of the five previous branches (read the "Left for review" parts of the Status sections of `plan_declare_less.md`, `plan_scientific_outputs.md`, `plan_agent_packaging.md` first).

## Items

1. **Display what numpy people actually return** — in `graphical/display.py::prepare_display` (the single conversion point for all backends and snapshots), so that no backend crashes and all show the same thing:
   - `(H, W, 1)` → shown as `(H, W)`; `(H, W, 4)` RGBA → composited on a checkerboard or white (decide, same everywhere); `bool` masks → 0/1; `uint8` → /255; `uint16` → /65535; other integer types: decide (clear error or scale) and document.
   - channel-first `(3, H, W)` / `(1, H, W)`, 4D batches, 0-size arrays, object arrays: cannot be guessed safely → an error naming the filter output with the fix, the same on every backend and in snapshots (today: a backend-specific crash naming nothing).
   - Then update `output_check` (the snapshot warnings added by `feature/declare-less`): cases that now display correctly everywhere must stop warning "the Qt and Dear PyGui backends raise on it"; it must know `Figure` / `Axes` / `Image` outputs.
   - Open decision from the last round, to settle with evidence: on the mpl backend a 2D array without colormap is shown with viridis while Qt, DPG, Gradio and snapshots show gray. Make gray the consistent default unless you find a reason not to; list it first in the changelog as a visible change.
   - Verify on the real backends offscreen (Qt grab, DPG if it can run headless, mpl Agg, snapshot) with one parametrised test over the array zoo.
2. **One error, once.** A failing filter prints a "PIPELINE ERROR" banner to stdout *and* raises `FilterError` carrying the same text, so a headless script or a test shows it twice (three times with logging). In headless calls, `snapshot`, `sweep` and the CLI: raise only. In a GUI event loop (where nothing catches it): show it once. Check what each backend does when a filter raises during a slider move: the window must survive and show the error (and recover on the next valid value).
3. **Error wording leftovers**
   - `@interactive(gain=(5, [0, 3]))` → say the default is outside the range (today "min=5 max=[0, 3] - max parameter should be numerical too").
   - `TypeError: Expected <class 'float'>, got <class 'str'>`-style messages anywhere a control name is available must name it; grep for remaining messages that name neither filter nor parameter.
   - `layout.style(...)` / `context[...]` outside a filter: the "Framework operation called outside of filter execution" message should say which call and show the two-line fix.
   - In the error for a wrong output count, the filter is named by its alias in the pipeline body; when the function name differs, give both.
4. **Process state**: controls are registered globally per function qualname, so (a) two scripts run in one interpreter with same-named `__main__` filters collide (`process_image: hue_shift not in ...`), (b) two pipelines built from the same filter share the control object, so a value set in one becomes the start value of the other. Fix (a). For (b) write a failing-or-passing test that documents the behaviour, then decide: per-pipeline control clones are probably right (the first round already clones for literal kwargs: `Control._clone_with_default`); if the change is too invasive for the time left, document it in the guide and Status instead.
5. **Import cost**: `import interactive_pipe` loads matplotlib (and `interactive-pipe --help` with it). Measure (`python -X importtime`), make the heavy imports lazy where it is safe, add a test that `import interactive_pipe` does not import `matplotlib.pyplot` nor any GUI toolkit, report before / after.
6. **Docs build**: `mkdocs build --strict` has never been run on these branches. If mkdocs with the project's doc dependencies fits in a throwaway venv under `/Data/` (check free space first: skip and say so if less than 2 GB would remain), build, fix every warning (broken links, pages missing from nav, bad anchors), delete the venv. Otherwise check links and nav with a small script and say what was not verified.
7. **Consistency pass** over `docs/` and `readme.md`: the five branches each added pages; make sure the same thing is not explained three times with different wording, that every public name mentioned exists (`grep` each code-formatted name against the package), and that the API reference lists the new public API (`PipelineSyntaxError`, `snapshot`, `sweep`, `describe`, `summary`, `draw`, annotation controls, `skill_path`, CLI).

## Ownership

Yours: `src/interactive_pipe/graphical/display.py`, `headless/snapshot.py`, `headless/explore.py`, `headless/control.py`, `core/`, `helper/`, `agent/command_line.py`, `cli.py`, `__main__.py`, `docs/` except the pages named below, `readme.md`, `mkdocs.yml`.
Not yours: event handling and widgets in `graphical/*_gui.py`, `*_control.py`, `qt_image.py`, `qt_viewer.py`, `dpg_*.py`, `mpl_window.py`, `gradio_*.py` (the pointer-input agent rewrites parts of them: for item 2 keep your edits there to the few lines that catch and show the error); the skill files and `demo/gallery/`, `docs/gallery.md` (the dogfooding agent); `docs/guide/mouse-input.md`.

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
