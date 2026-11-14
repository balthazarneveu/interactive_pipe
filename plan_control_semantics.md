# Plan: control and execution semantics found missing by the dogfooding round

Branch `feature/control-semantics`, based on `integration/next-level`. Read the friction log in the Status of `plan_agent_dogfood.md` first (items 1, 2, 3, 4, 10, 13), and the "Left for review" of `plan_robust_display.md` and `plan_pointer_input.md`: this plan is those items. `demo/gallery/*.py` contains the workarounds an agent had to write; at the end, each workaround you made unnecessary must be removed from the gallery example (they are yours to edit for that purpose) and the example must get shorter.

## Items, most valuable first

1. **One control driving several filters** (log item 1, the most expensive one). Today the same declaration in two filters gives two sliders, the same `name=` raises `Duplicate control name`, and the workaround is an extra "parameters" filter. Design it so the obvious thing works: the *same Control object* passed to two `@interactive` decorators is one widget and one value (`band = RangeControl(...)`; `@interactive(band=band)` twice). Also consider the annotation form (a module-level `Band = Annotated[float, Control(...)]` alias used in two signatures). `describe()` must list it once with all its targets, `pipe(img, band=...)`, snapshot, sweep (one axis, caption once), tuning export / import, and all GUI backends must show one widget. Parameters named differently in the two filters must work. Decide what two *different* controls with the same explicit name do (keep the error, say how to share). Use it in `demo/gallery/frequency_filtering.py`, `signal_filtering.py`, `pid_control.py` and delete their parameter-filter workaround.
2. **Per-pipeline control state** (review item 4b of the display round; reproducer `test_pipelines_built_from_one_filter_share_its_control`): two pipelines built from the same filter must not share values, unless the control is deliberately shared *within* a pipeline as in item 1. The display agent listed what has to change (`qt_panels.py:78`, `dpg_panels.py:109,128`, `gradio_layout.py:101` iterate `Panel._controls`). Do items 1 and 2 as one design; write the design in Status before coding.
3. **Snapshots and sweeps of stateful pipelines** (log item 4): each `snapshot` call and each sweep cell must start from a fresh `context` (the pipeline's initial context), so cells are independent and reproducible; the live pipeline's context must be untouched afterwards. Same for `events`. Add the reproducer of the log as a test. If a pipeline needs N warm-up runs, offer a simple way (`snapshot(..., runs=N)` or document calling the pipeline first with `fresh=False`) — choose the smaller API.
4. **Filters stay testable as plain functions** (log item 3a): `layout.style(...)`, `layout.grid(...)`, `context[...]` writes, `audio`, `events.get` called outside a pipeline run should not raise when the decorated filter is called directly (`compare(out, gt)` in a unit test): make layout calls no-ops and give `context` a plain dict for the duration of a direct call (reads of missing keys still fail clearly). Decide and document precisely; a call at module level outside any filter should keep failing with the improved message.
5. **Raw outputs from a GUI-decorated pipeline** (log item 3b): one obvious, documented way to get the arrays without opening a window from a `gui="qt"`-decorated pipeline, e.g. `pipe.run(img, gain=2.0)` returning the outputs like a `gui=None` pipeline does (check what `.headless` / `.pipeline` attributes already exist and pick one name; make the wrong guesses fail with a pointer to the right one).
6. **Data-dependent list unpacking** (log item 2): `out = f(x)` where `f` returns a *list* behaves differently for 0, 1, 2+ items. Make it depend on the pipeline line only: a single assigned name receives the returned object as is when it is a list (lists are data); tuples keep today's rule (a `return a, b` assigned to one name is an error that names the fix). Check every demo, sample, doc block and gallery example against the new rule, and list the change first in the changelog if anything observable changes.
7. **Log-scale and nicer sliders** (log items 10, 13): `Control(1e-2, [1e-4, 1e-1], scale="log")` and the shorthand / annotation forms (`(1e-2, [1e-4, 1e-1], "log")` is ambiguous with the label: choose a clean spelling such as `Annotated[float, (1e-4, 1e-1), "log"]` only if unambiguous, otherwise a keyword). The value shown, swept (`steps=` geometric) and saved is the real value. All backends (slider position is log, label shows the value). Default float step: round to 1/2/5 × 10^k close to range/100 so values read `0.05`, not `0.0195`.
8. **Pointer `on=` checked at build** (pointer round): call `interactive_pipe.headless.pointer.check_targets` at the end of `HeadlessPipeline.from_function`, with a test.
9. Small: `headless/animation.py` passes the output / filter name to `prepare_display`; docstring for `HeadlessPipeline.__call__`; type `save_entire_buffer`.

## Ownership

Yours: `src/interactive_pipe/core/`, `headless/` except `snapshot.py`, `helper/`, the panel builders named in item 2 and the control widget files `graphical/*_control.py` (item 7), `demo/gallery/*.py`, `docs/guide/controls.md` and a new `docs/guide/testing.md` if useful.
Not yours: `graphical/display.py`, `headless/snapshot.py`, `data_objects/`, `draw.py`, image / viewer / window files (a display-polish agent works there); `agent/`, the skill files, `docs/guide/examples.md`, `docs/guide/cli*.md` (a CLI agent works there). Put the lines the skill needs in Status.

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
