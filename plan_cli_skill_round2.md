# Plan: command line and skill, second round

Branch `feature/cli-skill-round2`, based on `integration/next-level`. Read the Status sections of `plan_agent_dogfood.md` (items 11, 12 and "Left for review"), `plan_pointer_input.md` ("Lines for the packaged skill") and `plan_robust_display.md` (skill lines that are now outdated).

## Items

1. **CLI after a filter error** (log item 11): `interactive-pipe snapshot err.py` prints the error then claims no pipeline was called. Say what happened (`pipeline 'p' raised FilterError, see above`), exit code 1; make sure the error is printed once.
2. **Set parameters from the command line** (log item 12): `interactive-pipe snapshot script.py --set t=4 --set gain=2.0 --set mode=dark --set seed=0.2,0.4`, values parsed against the control's type, unknown names fail with the list and a suggestion (reuse the library's resolver, do not write a second one). Also `interactive-pipe sweep script.py --param gain=0.5,1,2 [--param mode=dark,light] [--output err] -o sweep.png` so an agent can sweep an unmodified script. `describe --json` if not there yet.
3. **A `check` command for agents**: `interactive-pipe check script.py` = build every pipeline of the script without running a GUI, run it once with its defaults, and report in one screen: pipelines found, controls, outputs with shape / dtype / range, every warning the library can give (undisplayable or misleading outputs, clamped values), and errors with file and line. Exit code non-zero on error. Optional `--json`. This is the command a coding agent runs after every edit; make its output short and stable, and test it on a good script, a script with a `PipelineSyntaxError`, one whose filter raises, and one with a misleading output.
4. **Skill catch-up** (packaged skill is the source of truth; re-install the `.claude` copy with `python -m interactive_pipe skill --install --project . --force`; every code block is executed by `test/test_skill_code_blocks.py`; the line limit there may be raised to 260 if needed, but first remove what the dogfooding agent said it never needed):
   - mouse input section from the pointer plan's proposed lines, with a runnable block;
   - outputs line: RGBA, `(H, W, 1)`, uint8 / uint16, bool masks, figures now display the same on every backend; update the error table to the current messages (run each documented mistake and paste the real message);
   - the `check` command at the top of "Check your work without a display";
   - a short "testing your filters" paragraph.
   Verify by doing: with only the skill, write one new small example using mouse input + a figure + a colorbar, and report whether the skill was enough.
5. **Examples page**: add `pointer_demo.py`, `matplotlib_figure_demo.py`, `overlay_demo.py` and the gallery to `docs/guide/examples.md`; make the readme's feature list mention (one line each, with one image at most) snapshots / sweeps, controls from type hints, figures / overlays, mouse input, the command line and the skill. Keep the readme short: it is the first thing people see; move anything long to the docs.
6. **Upgrade notes**: a `docs/upgrade-0.10.md` (or the right name for the next version — do not bump the version, just name the page "Upgrading from 0.9") listing every behaviour change of the "Unreleased" changelog with before / after code, so a user with existing pipelines knows what will now raise. Run the before code of each entry on the base version mentally and the after code for real in a test.
7. **Changelog edit**: "Unreleased" is now very long (seven branches). Reorganise it for a reader: behaviour changes first (complete, each with the fix), then features by theme, then fixes. Do not drop information; this is the one file where a larger edit is expected from you — the two sibling agents only append short sections at its end.

## Ownership

Yours: `src/interactive_pipe/agent/`, `cli.py`, `__main__.py`, both skill files, `readme.md`, `docs/index.md`, `docs/guide/examples.md`, the CLI guide page, the new upgrade page, `CHANGELOG.md` (reorganisation), `mkdocs.yml` nav.
Not yours: the rest of `src/interactive_pipe/` (two sibling agents: control semantics in `core/`, `headless/`, `helper/`; display polish in `graphical/`, `data_objects/`, `draw.py`). If the CLI needs something from the library, use the public API; if it is missing, write it in Status.

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
