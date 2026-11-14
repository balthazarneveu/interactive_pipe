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

### Design of items 1 + 2 (written before coding)

- **A pipeline owns its controls.** `HeadlessPipeline.from_function` clones every
  registered control (`_clone_unconnected`, same name / default / panel) into the
  pipeline; the registered control (`Control.get_controls(f)`) is a declaration
  that no pipeline connects nor mutates. Two pipelines built from one filter
  therefore never share values; a direct call `f(img)` uses the declared
  defaults (a plain function, item 4). Repeats keep their `gain_1` clones,
  literal kwargs their `_clone_with_default`.
- **Sharing = the same declaration.** Clones are memoised per pipeline by a
  *share key*: the identity of the declared `Control` object. The same object
  passed to two decorators (`band = RangeControl(...)`; `@interactive(band=band)`
  twice) is one key, so one clone, one widget, one value, bound to several
  `(filter, parameter)` *targets* (parameter names may differ). Repeats of a
  filter get their own key per instance (`band_1`, shared among the `_1`
  instances).
- **Annotation alias**: `Annotated[float, Control(...)]` is cloned per function
  today and a plain alias (`Gain = Annotated[float, Control(1.0, [0, 3])]`) is a
  reusable *type*: kept per filter. An alias whose control has an explicit
  `name=` (`Band = Annotated[tuple, RangeControl(..., name="band")]`), which
  raised `Duplicate control name` when used twice, is now shared (the per-function
  clones carry the original's share key). Different signature defaults for one
  shared control raise at build (one widget has one default).
- **Control targets**: `Control.targets` (list of `(filter, parameter)`);
  `filter_to_connect` / `parameter_name_to_connect` stay as the first target.
  `update`, the parameters setter, `update_parameters_from_controls`, override
  resolution (`pipe(img, band=...)`, snapshot, sweep), `describe` (`targets`
  list, summary `-> a.band, b.bounds`), tuning import / export go through
  `targets`.
- **Two different controls with the same explicit name**: still an error; the
  message now says how to share (pass the same object).
- **Panels**: GUIs build a panel's widgets from `panel` members that are in the
  window's own control list (`Panel.controls_among(controls)`), not from the
  process-wide `Panel._controls`, so another pipeline's clones never show up.
- Auto-renaming of colliding names (`f.gain`, `g.gain`) never renames a shared
  control (it is renamed as a whole, keeping one clone).

### Done (2026-11-14, 04:06 → 05:00 CET)

Full suite green: 1516 passed, 6 skipped (ruff format + check clean). The only
failure seen in between was the known flaky
`test_command_line.py::test_doctor_opens_no_window` (pre-existing, see
`plan_robust_display.md`), which passed when rerun.

| Commit | Item | What |
|---|---|---|
| `73c4198` | 1, 2 | Each pipeline clones the declared controls (`from_function`, filter entry points); the same `Control` object in several filters = one clone with several `targets`; named annotation aliases shared; parameters setter, `update_parameters_from_controls`, overrides, captions, `describe` (`targets`), summary go through targets; Qt / DPG / Gradio panels build from `Panel.controls_among(window controls)`; clones no longer appended to `Panel._controls` (no leak, no foreign widgets). Duplicate explicit names still raise, with how to share. Tests: `test_shared_controls.py` (headless + all five backends), rewritten `test_pipelines_built_from_one_filter_do_not_share_its_control`. |
| `45dcfd4` | 1 | Gallery: `frequency_filtering` (shared `BAND`, `choose_band` removed, 81 → 78 lines), `signal_filtering` (shared `CUTOFF`, the invisible `context["cutoff"]` write/read removed; 98 → 98 lines), `pid_control` (named aliases `Kp`/`Ki`/`Kd`, `gains` filter removed, 87 → 79). Test: one control per shared value with both targets. |
| `d4cb2d0` | 3 | `PipelineCore` keeps the context given from outside (construction + `context=`) as the seed; `snapshot` and each sweep cell restart from it (events off, cache cleared), live context / events / cache restored afterwards. Warm-up: `runs=N` on snapshot / sweep (smaller API than a `fresh=` flag). Log reproducer in `test_stateless_snapshots.py`. `reaction_diffusion` no longer keys its state on (feed, kill) (62 → 60). |
| `3cc6b5c` | 4 | `core.context.direct_call_scope`: an `@interactive` filter called outside a pipeline run gets a throwaway framework state (layout / audio validated then no-ops, events off) and a scratch context whose missing keys raise a `KeyError` saying the filter is called directly. Module-level calls still raise (message names both ways). Gallery test calls the ISP filters directly. |
| `311226f` | 5, 9 | Chosen name: **`.headless`** (`HeadlessPipeline.run()` already exists without arguments, so `run` would mean two things). Every `@interactive_pipeline` function gets `.headless`, a separate `HeadlessPipeline` of the same function (the GUI reshapes its own pipeline's outputs into rows, so sharing it would not return what `gui=None` returns); `HeadlessPipeline.headless` is itself. `.run / .outputs / .results / .compute` on the launcher raise pointing to it. `HeadlessPipeline.__call__` docstring. |
| `42fa675` | 6 | A list returned to a single assigned name is kept whole (several names still unpack; tuples unchanged). Instrumented run of the whole suite (every demo, gallery example, sample and tested doc / skill block): no code relied on the old rule; untested doc blocks checked by hand (all are pipeline returns). Listed first in the changelog. Tests: `test_list_outputs.py` (the log reproducer for n = 0..3). |
| `72b690e` | 7 | `Control(..., scale="log")`, shorthand `(1e-2, [1e-4, 1e-1, "log"])`, annotation `Annotated[float, (1e-4, 1e-1, "log")]` (the label stays a separate string, so `"log"` in the step slot is unambiguous); float only, positive range, no step. `to_position` / `from_position` / `snap` on `Control`; Qt, DPG (slider over the position, its text the real value), matplotlib (valtext), notebook (`FloatLogSlider`), Gradio (HTML slider like the range one). Geometric `steps=`, `describe()["scale"]`. Default float step 1/2/5×10^k (`nice_step`), snapped values without float noise. `optimizer_trace`: `lr` log slider instead of `log_lr` (79 → 79 lines, the `10**` gone). Tests: `test_log_controls.py`. |
| `9b15239` | 8, 9 | `check_targets` at the end of `from_function`; `animation.py` passes output and filter names to `prepare_display`; `save_entire_buffer: bool`. Tests: `test_build_checks.py`. |
| `cc02aac` | — | `docs/guide/testing.md` (direct calls, `.headless`, fresh snapshots, `runs=`), blocks run in `test_testing_docs.py`; nav entry. |

Looked at: Qt offscreen grabs (shared control in its panel; log slider at mid
travel = 0.00316), matplotlib figure of the log slider, snapshots of the three
shared-control gallery examples (shared values captioned once), reaction-diffusion
sweep (independent cells), geometric `lr` sweep of `optimizer_trace`.

### Decisions worth knowing

- A pipeline **starts from the declared control's current value** (normally its
  default); repeats and renamed controls start from the default. The declared
  object is never connected nor changed by a pipeline, so `Control.get_controls(f)`
  is a declaration, and direct calls use it.
- `"filter.param"` naming one target of a shared control sets the control, hence
  all its targets (one widget, one value).
- A shared control is never auto-renamed (`band` stays `band` next to another
  filter's `band`, which becomes `f.band`).
- Single-filter entry points (`f.snapshot`, `f.interact`) still deduce their
  outputs by unpacking a returned list (no pipeline line to decide).
- Log scale is not offered for `RangeControl`, int sliders or `CircularControl`.

### Not done / limits

- Dear PyGui: the log slider text was checked by the unit test (the item's
  `format` is the real value), but the frame capture of a real viewport came back
  blank on this machine (twice), so it was not looked at as a picture.
- Gradio's HTML log slider: built and wired (the component value is the real
  value, `run_fn` sets the control), not rendered in a browser.
- `signal_filtering.py` and `optimizer_trace.py` did not get shorter in lines
  (the workaround lines were replaced one for one); `blob_detection.py` keeps its
  dict-of-columns design (a list-of-dicts rewrite was 3 lines longer), only the
  "a dict: one output" workaround comment is gone.

### Left for review (files not mine)

- **Skill** (`src/interactive_pipe/agent/build-interactive-pipeline/SKILL.md`), lines to replace:
  - l.75 "No log-scale slider: ..." → "Log slider: `lr=Control(1e-2, [1e-4, 1e-1], scale="log")`, `(1e-2, [1e-4, 1e-1, "log"])` or `Annotated[float, (1e-4, 1e-1, "log")]`; values, sweeps and captions are the real value."
  - l.77 "One slider for several filters: ... `pid = gains()` ..." → "**One slider for several filters**: declare it once and pass the same object to each decorator (`band = RangeControl(...)`; `@interactive(band=band)` on both; parameter names may differ), or a named annotation alias `Kp = Annotated[float, Control(2.0, [0, 10], name="Kp")]`."
  - l.104 "A returned tuple or list is unpacked ... 1-item list silently becomes its item" → "A returned tuple is unpacked into the names the line assigns; a list assigned to one name stays one value (detections...)."
  - l.219 row `returned 9 values but the pipeline assigns 1 name(s)` → fix: "the filter returned a tuple: unpack it, or return a list / `(items,)`".
  - Add: "Unit tests: call filters directly (`layout` / `context` work, context is a scratch dict); `my_pipeline.headless(img, gain=2.0)` returns the outputs of any GUI pipeline; snapshots / sweeps start from a fresh context, `runs=N` for warm-up."
- `docs/gallery.md` l.61 "a log10 learning-rate slider" → "a log-scale learning-rate slider"; l.105 (reaction-diffusion) → "the state lives in `context`; snapshots and sweeps start each picture from a fresh context, so they stay reproducible". Gallery PNGs (`scripts/make_gallery.py`) can be regenerated (optimizer captions now `lr=...`).
- `graphical/qt_gui.py::update_label` formats floats as `f"{val:.3e}"` (`3.160e-03`, `2.500e-01`): `f"{val:.4g}"` would read better now that steps are 1/2/5.
- `graphical/gui.py` / backends: `demo.pipeline.run(img)` (the GUI object's `run`) still fails with `TypeError: run() takes 1 positional argument`; a pointer to `demo.headless(img)` there would close the last wrong guess.
- `docs/guide/snapshots.md` / `decorators.md` (not mine) do not mention the fresh context / `runs=` nor the list rule; `docs/guide/testing.md` and the changelog do.
- Ruff reformats python blocks inside `plan_agent_dogfood.md` on every `ruff format .` (reverted each time here).
