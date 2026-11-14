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

Done, all on `feature/consolidate` (19 commits after `a5b7202`). Suite green:
1913 passed, 12 skipped (was 1880 + 12); ruff clean; pyright 8 errors (the 8
of `feature/next-level`); `mkdocs build --strict` passes (throwaway venv under
`/Data/`, deleted). Not pushed, not merged, version unchanged.

### Part 1 — leftovers

| # | Commit | What |
|---|---|---|
| 1 | `9debda6` | Qt `update_label` already used the shared formatter; the strays were the matplotlib log slider (`.3g`), the Dear PyGui log slider (`.3g`) and dial (`.2f`: a 0.005 dial showed `0.01`). All go through `format_number`. |
| 2 | `05e7c9b` | `demo.pipeline.run(img)` (any backend) raises `TypeError: InteractivePipeQT.run() takes no inputs: it starts the window's event loop. To get the outputs without a window, call demo.headless(img, gain=2.0) ...` (wrapper installed in `InteractivePipeGUI.__init__`). |
| 3 | `efe4a71` | Sweep default cell: the first image among the outputs downstream of the swept filters (`explore.outputs_downstream_of`, data-flow graph), else the first such output, else the last image. CLI follows (same code). Skill sentence, snapshots / command-line guides, changelog feature line updated. Looked at the PNG (`return img, out` sweep shows `out`). |
| 4 | `ce1012f` | Clamped override warned once: `apply_overrides` sets the control through `Control._set_value_caller_reports_clamp` (no "outside its range" log), and keeps its own `snapshot(): gain=7 is outside the range ...` warning. `check --set gain=5` lists one warning. |
| 5 | `4f94a93` | Why: `layout.grid` rebinds `pipeline.outputs`, which was both the display layout and the shape of the call's result. Now `PipelineCore.returned_outputs` keeps the function's `return`: `pipe(...)`, `.headless(...)`, `save()` follow it; `run()` / `results` (windows, snapshots) still follow the grid. Behaviour change vs 0.9.4 (checked on its source): changelog first section + upgrade page section `layout.grid no longer changes what a call returns`; skill sentence updated. |
| 6 | `ac77535` | Under `QT_QPA_PLATFORM=offscreen` only, a Qt message handler (`qt_backend.quiet_offscreen_messages`) drops the `propagateSizeHints()` notice and forwards every other Qt message to stderr (subprocess test). Chosen over not building the Qt object: scripts configure `demo.pipeline` (key bindings...) under snapshot. |
| 7 | `6219016` | `label` registered in `SUPPORTED_STYLE_KEYS` (the display already read it; same as `colorbar="text"`); `unit` / `dpi` docstrings fixed; `figures-and-overlays.md` table row. PNG looked at. |
| 8 | `b99ae3c` | `blob_detection`: no `or None`, no `.tolist()`, no "no detection" string (empty `Table`, test updated); `figsize` removed from `optimizer_trace` and `pid_control` — the Bode plot then lost its labels because the demo called `fig.tight_layout()` itself (kept at the old size): call removed, the library lays it out. `frequency_filtering`: the long text `log10 \|FFT\|` went to `colorbar="..."` (along the bar) rather than `unit=` (meant for a short unit above the bar). `docs/gallery.md` two sentences. All 11 PNGs regenerated and looked at. |
| 9 | `524de64` | `snapshots.md`: fresh context, `runs=`, a `.headless` section with the list rule; `decorators.md`: "What a filter returns, what a call returns". |
| 10 | — | `mkdocs build --strict`: no warning, before and after this round's doc edits. |
| 11 | `cc8f640` | pyright 54 errors on the branch vs 8 on `feature/next-level` (same command: `pyright --pythonpath <shared venv python>`, the worktree has no `venv/`). The 46 new ones fixed (Optional narrowing in DPG / gradio / mpl / Qt overlay code, `Any` for point / region tuples, Control's per-instance attributes declared). |

### Part 2 — review

Fixes (each with tests):
- `e826c13` parser: ~70 unusual pipeline functions probed (probe script kept out of the repo; a representative subset is in `test/test_pipeline_parser_robustness.py`). Work: stacked `functools.wraps` decorators, bound methods, `@staticmethod` over the decorator, nested in `main()`, `async def` (body parsed only), annotated assignment `out: T = f(img)`, `[a, b] =` / `(a, b) =` targets, 400-line bodies, one-line `def`, semicolons. `PipelineSyntaxError` with hint: walrus, star targets / args, `**kwargs`, nested tuple targets, chained assignment, attribute / subscript targets, bare annotations, `global`, `del`, `import`, `assert`, `class` / `def` / `match` in the body, `yield` / `await`, dict / starred returns, calls on call results, unknown attributes, non-callables, filters defined after the decorated pipeline. Were wrong and fixed: a pipeline called inside another (`TypeError ... implicit context injection was removed`), a pipeline calling itself (RecursionError at run time), `@interactive_pipeline` applied twice / `functools.partial` / callable objects / builtins (inspect's "module, class, method ... was expected"), a lambda (plain `ValueError`). An unbound method `A.p` gives `expects 2 inputs (self, img)` — clear enough.
- `10c32e5` two validators of `parameters={...}`: headless calls raised `TypeError` (explore), GUI calls `ValueError` (setter); the changelog / upgrade page promise `ValueError`. One validator, `ValueError` (TypeError only when `parameters` is not a dict), also run by GUI calls.
- `1571dfd` duplicated range validation: annotations re-implemented min <= max, step and default checks; now `Control`'s (wrapped with the annotation's function / parameter); only the int-hint checks stay.
- `85ecb2a` two value formatters (`snapshot.format_value`, `value_format.format_control_value`): one, `value_format.format_value`.
- `8b94b51` two "is this an image" checks: snapshot's `_image_array` now uses `display.array_display_problem` + `normalize_image`.
- `44d699e` the one mutable default added this month (`pointer_input._warn_once`). No `assert` for validation, no debug print (all `print` calls are CLI output), no TODO added this month.
- `22d9e63` behaviour changes: the `feature/next-level` test-suite (`git archive` into the scratchpad, run against this source) gives 16 failures / 697 passed. Listed in the changelog already: duplicate auto-named controls renamed (1), reworded default-outside-range message (1). Added to the changelog by this commit (new bullet "More reworded messages and one exception type"): input-count messages (4), filter output-count messages (2), control value messages and the unsupported-default-type message (4), `PipelineCore(filters=[])` `ValueError` instead of `IndexError` (1), Qt slider label `0.5` instead of `5.000e-01` (1). Not API (internal or visual, not listed): Gradio `run_fn` gives tables as `{"headers", "data"}` (1), the matplotlib error cell text is wrapped on two lines (1). No regression found.
- `63c0fd6` `PointControl`, `RegionControl`, `to_pixels` were on no `docs/api` page; `test/test_api_docs.py` now checks every `__all__` name.
- `0ba4a93` `code_architecture.md` (modules added this month, return order vs layout), `tech_debt.md` (open judgement calls below).

Performance (slider move = set `gain`, run, display; 3 filters, 1024 x 1024 x 3 float32, median of 35 moves, two runs each):

| | `feature/next-level` | now |
|---|---|---|
| headless `pipe(img, gain=v)` | 10.8 ms | 8.6–8.8 ms |
| Qt offscreen `update_parameter` + `refresh` + `processEvents` | 23.3–23.5 ms | 22.4–23.3 ms |

Nothing to fix (no slower path measurable).

### Public API added since `feature/next-level`

| Kind | Name | Docstring | In `docs/api/` |
|---|---|---|---|
| `__all__` | `PipelineSyntaxError`, `PointControl`, `RegionControl`, `to_pixels`, `draw` (module), `skill_path` | yes | yes (Point/Region/to_pixels added here) |
| `HeadlessPipeline` | `snapshot`, `sweep`, `describe`, `summary`, `headless` (property, itself), `load_tuning` (alias of `import_tuning`), `save_run_state`, `restore_run_state`, `restart_run_state`, `returned_outputs` (attribute) | yes | via `::: HeadlessPipeline` |
| GUI-decorated pipeline function | `.headless`, `.snapshot`, `.sweep`, `.describe`, `.summary`; `.run` / `.outputs` / `.results` / `.compute` raise pointing to `.headless` | yes | in `interactive_pipeline`'s docstring |
| `@interactive` function | `.snapshot`, `.sweep`, `.describe`, `.summary`, `.interact` | yes | guide (`snapshots.md`), not an API page |
| Control options | `Control(scale="log")`, `(v, [lo, hi, "log"])`, one `Control` object shared by several filters, `Annotated[...]` / `Literal` / `Enum` hints, `PointControl(on=)` | yes | yes |
| `layout.style` keys | `subtitle`, `colormap`, `vmin`, `vmax`, `center`, `colorbar`, `label`, `unit`, `dpi`, `xlabel`, `ylabel` | in `layout.style` docstring | `figures-and-overlays.md`, `layout.md` |
| Snapshot / sweep keywords | `output=`, `params=`, `inputs=`, `figsize=`, `dpi=`, `title=`, `caption=`, `runs=`, sweep `steps=` | yes | yes |
| CLI | `interactive-pipe snapshot` / `sweep` / `describe` / `check` / `skill` / `doctor`; `--set`, `--param`, `--steps`, `--output`, `-o`, `--pipeline`, `--max-calls`, `--json`, `--install`, `--user`, `--project`, `--force`, `--path`, `--agents-md`, `--version` | `--help` | `command_line.main` + `guide/command-line.md` |
| Environment | `INTERACTIVE_PIPE_SNAPSHOT` (new); `INTERACTIVE_PIPE_GUI`, `_SIZE`, `_DEBUG` existed | — | `guide/snapshots.md`, `command-line.md` |

Naming: `snapshot` / `sweep` / `describe` / `summary` / `headless` / `check` are consistent between pipelines, filters and the CLI. Judgement calls for the maintainer: `params=` (snapshot / sweep, flat `{name: value}`) vs `parameters=` (call, nested `{filter: {param: value}}`) — different shapes, similar names; `output=` (snapshot / sweep) vs `output_indexes=` (`save`, older); snapshot takes no `context=` while a call does; `DisplayError` is raised to users but not exported from `interactive_pipe`.

### Not done

- No interactive check of a real window (offscreen Qt and PNGs only, as planned).
- Two ways left on purpose: `headless/pipeline._as_image_array` (save: keeps RGBA for PNG) vs `display.normalize_image` (display: composites RGBA) — same dtype rules, different output; listed in `tech_debt.md`.

### Left for review

- **Unassigned call to a value-returning filter raises** (same on 0.9.4):
  ```python
  @interactive()
  def f(img):
      return img * 2

  def p(img):
      f(img)          # FilterError: filter 'f' returned a single ndarray but the pipeline unpacks 0 values
      return img
  ```
  The docs list `log_stats(img)` as accepted, which holds only for a filter returning None. Keep (catches a forgotten assignment) or drop the value like Python — and say so in `decorators.md`.
- **User-laid-out figures are not laid out again at cell size**: a figure on which the filter calls `fig.tight_layout()` at its `figsize` keeps those margins when drawn in a smaller cell, so labels can be cut (seen on `pid_control`, fixed in the demo by not calling it). `graphical/display.py::rasterize_figure` could re-run `tight_layout` when the figure has no layout engine, at the cost of overriding a deliberate `subplots_adjust`.
- Colorbar ticks: with `vmin=1.0` and max 4.2 the strip shows `4.2` and `4.0` almost touching (`frequency_filtering.png`); readable, not overlapping.
- The native crash seen once in a full-suite run in an earlier round happened once here too (first full run after the clamp change, `Fatal Python error` with PyQt6 / dearpygui loaded); every later full run passed. Not reproduced.
- Sibling ownership: the skill was edited for the sentences of items 3 and 5 only (sweep default; `.headless` returns `return` order whatever `layout.grid` shows) and re-installed with `skill --install --project . --force`.
