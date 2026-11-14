# Plan: third dogfooding round — porting existing scripts and debugging broken pipelines, then fixing what hurts

Branch `feature/port-and-debug`, based on `integration/next-level`. The two earlier rounds (`plan_agent_dogfood.md`, `plan_agent_dogfood_2.md`) tested writing new tools from scratch. Real use is different: a person or an agent has an existing analysis script full of matplotlib and magic constants and wants sliders on it; or has a pipeline that does not behave and must find out why. This round tests those two, and — unlike the earlier rounds — you fix the library yourself.

## Part A — porting (measure, then fix)

Write five ordinary, slightly messy analysis scripts the way people write them (module-level code, constants at the top, `plt.subplot` / `plt.imshow` / `plt.plot` / `plt.show()`, loops over parameter values, helper functions returning several things, in-place edits) under `demo/porting/before_<name>.py` — e.g. a denoising comparison, a spectrogram with window parameters, a camera-response / tone-curve fit, a PCA or clustering scatter, an edge-detector comparison with thresholds. Synthetic data only, no new dependency.

Then, reading ONLY the packaged skill (`src/interactive_pipe/agent/build-interactive-pipeline/SKILL.md`), port each to `demo/porting/after_<name>.py`. Measure: lines before / after, lines that could be kept verbatim, minutes, every place where the port needed restructuring that the library could have absorbed (module-level arrays as pipeline inputs, loops over parameter values → sweep, `plt.subplot` grids → return layout, existing figures → `Figure` outputs, constants → controls, in-place edits vs read-only inputs, helper returning a dict...). The log of those is the first deliverable.

Then fix the top items in the library. Candidates to evaluate (do the ones your log supports, not all of them blindly):
- a filter written with `pyplot` (`plt.figure(); plt.plot(...); return plt.gcf()`) should just work and leak nothing — check what happens today on each backend;
- a one-call way to try a *single function* with sliders without writing a pipeline (`interact` exists: is it in the skill, does it take annotations, does it snapshot?);
- constants → controls: `interactive-pipe` could suggest controls for a function (`describe` on an undecorated function listing its numeric keyword arguments with a proposed range), if that helps an agent;
- an "inputs" story for module-level data: a pipeline with no parameter that calls a loader filter is the documented way — is it obvious from the errors when someone passes a global array inside the body instead?
- a migration section in the docs: `docs/guide/porting-a-script.md` with one before / after from your five, tested.

## Part B — debugging (measure, then fix)

Write eight broken pipelines under `test/broken_pipelines/` (not collected as tests), each with one realistic bug whose *symptom* is visual or silent rather than an exception: a control wired to the wrong parameter name through `**kwargs`; a filter that mutates its input in place; a stale result because a filter reads a global that changed; float image in 0–255; BGR/RGB swap; an off-by-one crop that changes the output size between runs; a control whose range makes it a no-op (integer division); a `context` key written after it is read; a cached filter with a non-deterministic input; NaNs appearing only for some slider values.
For each: starting from the symptom only, use the library's tools (`interactive-pipe check`, `describe`, `snapshot`, `sweep`, `.headless`, `.styles`, logging) to localise the bug. Measure how many tool calls it took and whether a library tool pointed at the cause or you had to add prints. The log is the second deliverable.

Then build what was missing. Candidates (again, only what the log supports):
- `check` / a `--trace` option reporting, per filter: ran or cached, time, output shape / dtype / min / max / NaN count, which controls it read — so "which filter produces the NaN / the size change / the wrong range" is one command;
- `sweep` reporting which outputs did not change across the swept values ("gain has no effect on any output": a no-op control is a bug nine times out of ten), in `check` too (perturb each control once: cheap for small pipelines, opt-in flag otherwise);
- in-place mutation of an input: inputs are read-only by default already — verify the message names the filter and line and suggests `.copy()`;
- intermediate results: an easy way to snapshot *every* intermediate variable of the pipeline, not only returned ones (`snapshot(output="all")` — does "all" include non-returned variables? if not, add `intermediates=True` or similar);
- a `docs/guide/debugging.md` page walking through three of your broken pipelines with the commands and their real output (tested).

## Deliverables

- The two logs with numbers, in Status, written before the fixes; then for each fix, the same measurement again (tool calls before / after).
- Library changes with tests; `demo/porting/` (run headless in the test-suite like the other demos: check how `test/test_demos_headless.py` collects scripts and what it will do with `before_*.py`, which call `plt.show()` — they must not open a window nor be reported as demos without output; exclude them explicitly if needed), `test/broken_pipelines/` used by a test that asserts the tools now point at each bug.
- Skill: a short "Porting a script" and "Debugging a pipeline" part (the skill is near its line limit of 260 in `test/test_skill_code_blocks.py`: you may raise it to 290 for these two, or move rarely needed material to the docs and link it); re-install the copy with `python -m interactive_pipe skill --install --project . --force`.
- Changelog entries in the existing themed sections; any behaviour change needs an upgrade-page section (`test/test_upgrade_page.py` enforces the link).

## Ownership

Everything except: `test/conftest.py` and the threading / lifetime code of `graphical/qt_gui.py`, `qt_runner.py`, `dpg_gui.py`, `dpg_backend.py`, `gui.py` (a sibling agent is fixing a native crash there and loops the full test-suite many times: the machine is short on memory, so run the full suite one at a time, never several in parallel, and prefer targeted test files while iterating).

Finish by 10:30 CET even though the hard stop is 11:30: the branch has to be merged and checked after you.

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

Times are wall-clock from `date` (the five ports took about 2 minutes in all, as an agent: the
numbers below count lines and restructurings, which is what matters for a person).

### Log A: porting five scripts (before the fixes)

| script | lines before / after | kept verbatim | restructuring the library could absorb |
|---|---|---|---|
| denoise | 50 / 56 | helpers `shifted_stack`, `psnr` (10) + data lines (4) | module-level `rng` used by a filter -> new noise on every run (seeded inside the filter by hand); `plt.title(f"PSNR...")` -> `Image(title=)`, then the next filter receives an `Image` and needs `.data` (`layout.style(title=)` is the better advice, already in the skill); constants -> controls (4) |
| spectrogram | 37 / 57 | `stft` (8), signal generation (3) | `imshow(origin="lower")` has no `layout.style` equivalent -> `db[::-1]` by hand; `extent=` / labels map 1:1 to `layout.style`; `plt.subplots(2, 1)` -> `return [[wave], [db]]` |
| tone curve | 34 / 48 | `polyfit` body (3) | the loop over degrees becomes a slider + `sweep(degree=[1, 3, 5])`: the overlay of all degrees in one plot is lost; helper returning a dict -> filter returning a dict works as is (not displayed) |
| clusters | 35 / 50 | `kmeans` (6) and **the whole pyplot plotting block (7)** | the skill says "never pyplot", so an agent would rewrite the plotting to `Figure()`; the library actually renders `plt.subplots()` figures fine on every backend and in snapshots, **but headless calls leak one pyplot figure per run** (5 runs -> 5 open figures) |
| edges | 41 / 51 | `convolve3` (7), detector body (6) | `if SMOOTH:` module-level reassignment -> a checkbox filter; thresholds x detectors `plt.subplot` grid -> `sweep(threshold=[...], output=["sobel", "laplacian"])` reproduces it exactly |

Checked separately: a module-level array used in the pipeline body (`out = amp(NOISY)`) already
fails with "'NOISY' is not a variable of the pipeline ... Hint: add `NOISY` to the arguments of the
pipeline function" (good, kept). `my_filter.interact(img)` (one function with sliders, no
pipeline, snapshot-captured) exists but is not in the skill. A "suggest controls" command was not
needed: choosing ranges was never the slow part.

Fixes chosen from this log: pyplot figures returned by filters released after headless runs;
skill: pyplot is fine, a "Porting a script" part (inputs as arguments, loops -> sweep, subplot
grid -> return layout, seed random generators inside filters, `.interact`); a docs page.
`origin="lower"` and the lost overlay are left (see "Not done").

### Log B: debugging eight broken pipelines (before the fixes)

Tool calls counted from the symptom to the cause, using check / snapshot / sweep / headless.

| script (bug) | calls | did a tool point at the cause? |
|---|---|---|
| kwargs_wrong_name (`gain` control, filter reads `kwargs["strength"]`) | 1 | yes: `check` fails at decoration, file:line; message "does not match any of the function keyword args []" does not say controls are not passed through `**kwargs` |
| inplace_mutation (`img[img < t] = 0` on the input) | 1 | yes: filter, file:line, "assignment destination is read-only"; no hint that inputs are read-only nor `.copy()` / `inplace=True` |
| float_255 (`astype(float32)` keeps 0-255) | 2 | half: `check` warns on the returned output; the filter that changed the scale (`load`, an intermediate) is found by reading code |
| crop_size (crop height depends on zoom parity) | 5 | no: `check` silent at the default; snapshot / sweep look alike; the crop is not returned, so shapes were printed with a temporary `return crop` |
| noop_control (`sharpen // 10` is always 0) | 2 | half: `sweep sharpen=0..5` shows identical cells, if one notices; nothing says so |
| context_order (key read before the filter writing it) | 4 | no: snapshot / sweep cells start from a fresh context, so the overlay is always missing; found by reading code |
| nondeterministic (module-level rng) | 3 | no: needed a hand-written double run and array diff |
| nan_some_values (negative values ** (1/gamma)) | 4 | no: `check` at gamma=1 has no NaN (only a negative min); a sweep shows black areas; which filter -> prints |

Total 22 calls, 2 of 8 with a tool pointing at the cause.

Fixes chosen from this log: `check` runs a cheap diagnosis (per-filter trace of every intermediate
variable; each control perturbed once: no-op controls, NaN appearing, output size changing, with
the first filter where it happens; a second run with the same values: non-deterministic filters;
context keys read before written), `check --trace` prints the per-filter table, the same as
`pipe.diagnose(img)` in Python; better messages for `**kwargs` and read-only inputs.
