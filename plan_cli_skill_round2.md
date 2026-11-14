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

Done, 2026-11-14, 04:06 -> 04:45 CET, on `feature/cli-skill-round2` (nothing pushed, no PR, no merge, no version bump). Final suite: **1525 passed, 6 skipped** (baseline 1444 passed, 6 skipped); ruff format / check clean; `mkdocs build --strict` clean, also with nav / link / anchor validation raised to warnings (throwaway venv under `/Data/`, deleted).

### Commits

| Item | Commit | What |
|---|---|---|
| 1 | `b42d99d` | CLI after a filter error: `interactive-pipe snapshot: pipeline 'p' raised FilterError, see above` (or `(caught by the script): <message>`), exit 1; the script error printed once without interactive_pipe / runpy / site-packages frames (FilterError / PipelineSyntaxError keep their message + the script's call site); `describe` still describes a pipeline whose run failed; `run_script.error_location()`. |
| 2 | `09f7bbe` | `--set NAME=VALUE` (snapshot, sweep, check), `interactive-pipe sweep --param / --steps / --output`, `--pipeline NAME`, new `agent/parameters.py`. Names through `headless.explore.resolve_names` (the library's resolver: list + "did you mean"), values typed from `describe()` (control kind / type) or the default's type. Bad name / value: exit 2, nothing written. `--set` wins over the script's call values, which are kept. Also: the known-flaky `test_doctor_opens_no_window` now compares with the QApplication alive before (my Qt-decorated test scripts made it fail deterministically). `describe --json` already existed. |
| 3 | `cdd3d37` | `interactive-pipe check SCRIPT.py [--json] [--set]`, `agent/check.py`: pipelines, inputs, controls, outputs (type / shape / dtype / range / NaN count), warnings (output_check problems of the real run, clamped values, anything logged; environment noise dropped), errors with user file:line; also runs pipelines the script only defines when they take no input, lists the others as "not run (needs inputs)". Tests on a good script, a `PipelineSyntaxError`, a filter raising, a misleading output, an undisplayable output, defined-only pipelines, no pipeline, `--set`, `--json`, stable output. All 28 demos and gallery scripts: `OK` (multi_image: 1 warning, "Torch is not available"). |
| 4 | `c55631c`, `52c5237`, `1cb7b51` | Skill: mouse-input section with a runnable block, outputs line (RGBA, `(H, W, 1)`, uint16, bool, figures everywhere), error table with the current messages + `test/test_skill_error_table.py` (runs each documented mistake, checks the quoted text), `check` first in "Check your work", `--set` / sweep for scripts, "Testing your filters" with a runnable test, the wrong "default: the last output" fixed. Removed the `PipelineSyntaxError` example block (the dogfooding run hit zero of them); limit raised to 260 (259 lines). `.claude` copy re-installed. |
| 5 | `1a7cb4c` | Examples page: `pointer_demo.py`, pictures of the figure / overlay / pointer demos (`docs/images/pointer_demo.png`, quantized snapshot, 262 kB), the eight gallery scripts; readme "Features" list (type hints, figures / overlays, mouse input, snapshots / sweeps, command line, skill), one image (gallery sweep), 92 lines; `docs/index.md` lines; `test/test_examples_page.py`. |
| 6 | `faeb7bc` | `docs/upgrade-from-0.9.md` ("Upgrading from 0.9", nav after the changelog, in llms-full): every behaviour change with before / after; every "before" that now fails is a `raises` block (PipelineSyntaxError, FilterError, TypeError, ValueError, DisplayError) and every "after" runs (`test/test_upgrade_page.py`, 21 blocks); the test also checks every changelog behaviour bullet links to an existing anchor. |
| 7 | `fdee24c` | CHANGELOG "Unreleased" reorganised: 23 behaviour changes first (grouped: pipeline body, running, declaring controls, display, errors and logs), each with the fix and its upgrade-page link; then features by theme; then fixes. Checked that every code span of the old section is still there. |

Docs of the CLI (guide page `command-line.md` + `api/agent.md` table) are in the item 2 and 3 commits.

### Decisions

- **`-o/--out` is the path, `--output` selects outputs** (like `snapshot(output=...)`), as the plan's synopsis has it. The long form `--output` of the path existed only in "Unreleased": renamed `--out`, no deprecation.
- **How `--set` combines with the script**: each captured call is let through until the pipeline is about to run (inputs, script keyword arguments, `parameters=` / `context=` applied), the values are captured, then the command renders with its own options (`run_snapshot` / `sweep` with `"filter.param"` overrides). So `p(img, gain=0.5)` in the script plus `--set mode=light` gives both, and `--set gain=2` wins. The trick is a temporary instance attribute `pipeline.run` (no change to library files).
- **Several pipelines**: a name that only another pipeline of the script has is skipped for this one; a name no pipeline has fails with the resolver's message. A sweep whose names all belong to another pipeline skips this pipeline.
- **Sweep values**: comma-separated; `;`-separated for ranges / points / regions; repeated `--param NAME=` appends.
- **`check`** keeps output on stdout and the script's prints on stderr; exit 1 on any error, 2 on a bad `--set`, warnings never fail. The script now runs through `exec` in a module object kept on `ScriptRun.namespace` (same semantics as `runpy.run_path`), so pipelines defined by the script are found even when it raises.

### Skill verification (item 4, "verify by doing")

A fresh agent given only SKILL.md wrote `mouse_figure_demo.py` (57 lines: a `pick` filter returning a `PointControl` + `RegionControl` shared by two filters, a Figure with the row profile and the region histogram, a `RdBu_r` heatmap with colorbar centred on the clicked value). 2 `check` rounds (the first showed two independent `seed` controls, fixed with the skill's parameters-filter pattern), the snapshot right the first time, 3 sweeps correct. **Zero look-ups outside the skill; verdict: the skill was enough.** Gaps it reported, fixed in `52c5237`: whether the parameters-filter pattern works for mouse controls / `on=` a later output (yes, now said), "sweep = one row" (cells are laid out to fit), CLI `--output` accepting `all` / a list. Its remark that `draw.points(filled=False)` "is the default" was a misreading (the default is `filled=True`).

### Not done

- Nothing of the plan left. Not added: a `--strict` for `check` (warnings as errors) — not asked.

### Left for review (files not mine)

- **Qt offscreen noise in every CLI run**: `This plugin does not support propagateSizeHints()` on stderr, printed when `helper/pipeline_decorator._gui_for_snapshot` builds the (never shown) Qt GUI object. `QT_LOGGING_RULES="qt.qpa.*=false"` does not hide it; a `qInstallMessageHandler` filter in `graphical/qt_gui.py` (or not building the Qt window object under `INTERACTIVE_PIPE_SNAPSHOT` / the hook) would. Reproducer: `interactive-pipe check demo/key_event_demo.py`.
- **Sweep default output** (`headless/snapshot.default_sweep_cell`): the first image output, which for the usual `return img, out` is the input, so every cell looks the same (`interactive-pipe sweep script.py --param gain=0.5,1,2` without `--output`). Suggestion: the last image output. The skill now documents it.
- **Clamp warned twice** (`headless/explore.apply_overrides` + `headless/control`): `--set gain=7` (or `snapshot(gain=7)`) logs `Control 'gain': value 7.0 is outside its range ...` and warns `snapshot(): gain=7 is outside the range ...`; `check` lists both.
- **A filter calling `layout.grid` changes the return shape of a headless pipeline** (a list of rows instead of a tuple): surprising in tests (found while writing the skill's testing block); documented in the skill.
- `ruff format .` keeps rewriting python blocks in the other plan files (`plan_agent_dogfood.md`); reverted each time, not committed.
