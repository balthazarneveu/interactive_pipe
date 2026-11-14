# Plan: consolidation — leftovers of four rounds, then a whole-branch review

Branch `feature/consolidate`, based on `integration/next-level`, which now holds ten merged feature branches (about 1880 tests). You are the only agent changing the library in this round, so you own every file except the ones listed under "Not yours". A sibling agent is writing new examples from the skill alone at the same time and will report friction; do not wait for it.

## Part 1 — leftovers (each is in a "Left for review" list of a `plan_*.md` Status; read those lists, they have reproducers)

1. `graphical/qt_gui.py::update_label` still formats some floats as `3.160e-03`: use the shared value formatter (`graphical/value_format`) everywhere a control value is shown; grep the other backends for stray `:.3e` / `%.3e`.
2. `demo.pipeline.run(img)` on a GUI object fails with `TypeError: run() takes 1 positional argument`: make the wrong guess point to `my_pipeline.headless(img)`.
3. Sweep default output: the first image output is usually the input, so `sweep(..., gain=[...])` without `output=` shows identical cells. Choose the output that depends on the swept parameters (the graph knows which filters consume them: the first displayed output downstream of a swept filter; fall back to the last image output). Same for the CLI. Update the skill sentence that documents the old behaviour (tell the sibling's file ownership: the skill is yours for this sentence only).
4. A clamped value is warned twice (`headless/explore.apply_overrides` + `headless/control`): once.
5. A filter calling `layout.grid` changes the return shape of a headless pipeline call (list of rows instead of a tuple): find out why, decide what is least surprising (outputs returned in the pipeline's `return` order regardless of the display grid seems right), make it consistent between `pipe(...)`, `.headless(...)`, `save()`; if this changes behaviour, document it in the changelog's first section and the upgrade page (its tests require a link for every behaviour change).
6. `This plugin does not support propagateSizeHints()` printed on stderr by every offscreen CLI / snapshot run of a `gui="qt"` script: do not build Qt objects when only a snapshot is asked, or filter that message.
7. `core/context.py`: register `label` for colorbars if the display reads it; fix the outdated `unit` and `dpi` docstrings.
8. Gallery (`demo/gallery/*.py`): remove the workarounds the library no longer needs (`blob_detection`: `color=[...] or None`, the "no detection" string, `.tolist()`; hand-tuned `figsize`; `frequency_filtering` can use `unit=`); `docs/gallery.md` two outdated sentences (log slider, reaction-diffusion context); regenerate `docs/images/gallery/*.png` with `scripts/make_gallery.py` and look at each one.
9. `docs/guide/snapshots.md` and `decorators.md`: fresh context / `runs=`, the list rule, `.headless()`.
10. `mkdocs build --strict` again (throwaway venv under `/Data/`, delete it after; skip if less than 2 GB would remain free) — ten branches have added pages since the last run.
11. `pyright`: report the error count; fix what this month's branches introduced (compare with `feature/next-level`), leave the pre-existing ones.

## Part 2 — whole-branch review (`git diff feature/next-level...HEAD -- src/`)

Read the whole source diff as a reviewer who has to maintain it. Fix what is clearly wrong; list what is a judgement call. Look for:
- **Two ways to do one thing** introduced by different branches (two name resolvers, two value formatters, two "is this an image" checks, two places converting outputs for display, duplicated range validation between tuple shorthand / annotations / `Control`). Unify where the change is mechanical and covered by tests.
- **Public API coherence**: list every public name added since `feature/next-level` (`__all__`, methods on pipelines / filters, CLI options, `layout.style` keys, environment variables). Check naming is consistent (`snapshot` / `sweep` / `describe` / `summary` / `headless` / `check`; `output=` vs `outputs=`; `params=` vs `parameters=`), each has a docstring and appears in `docs/api/`. Write the table in Status: it is what the maintainer will review before releasing.
- **Behaviour changes**: verify the changelog's "Changes that can affect existing code" is complete by running the test-suite of `feature/next-level` (`git show feature/next-level:test/...` into a temporary folder) against the current source and explaining every failure: each one is either listed in the changelog or a regression to fix.
- **Performance**: time a slider move on a 3-filter pipeline with a 1024×1024 image, headless and through the Qt window offscreen, on `feature/next-level` and now (the new output checks, display conversion, context copies and control cloning all sit on that path). Report the numbers; fix anything that costs more than a few percent.
- **Robustness of the parser additions**: decorators stacked on pipelines, pipelines as methods or nested functions, async, type-annotated assignments, walrus, star-unpacking targets, very long bodies; filters defined after the pipeline; recursion. Each either works or raises `PipelineSyntaxError` with a useful hint — never a raw `KeyError` / `AttributeError` / `IndexError`.
- Dead code, leftover debug prints, `assert` used for validation, mutable defaults, TODOs added this month.
- Update `tech_debt.md` and `code_architecture.md` for the new modules (short, factual).

## Not yours

`demo/gallery/` files not listed in item 8 (the sibling adds new ones named `g2_*.py`), `plan_agent_dogfood_2.md`. The skill only for the sentences named above (re-install the copy: `python -m interactive_pipe skill --install --project . --force`).

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
