# Plan: fix the silent failures found in the 0.9.4 usability audit

Branch: `fix/silent-pipeline-failures` (cut from `feature/next-level` at `8213c59`).
Baseline before any change: `713 passed, 6 skipped` with
`QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg ./venv/bin/python -m pytest test/ -q`.

## Goal

A first-time user or a coding agent who makes a common mistake must get either
the behaviour they meant or an error that names the line and the fix. Today
most of these mistakes produce a pipeline that runs and is wrong.

Every row of the table below was reproduced headless (`gui=None`) on 0.9.4.
Each one needs a regression test that fails on the baseline.

| # | What is written | What happens today | Target |
|---|---|---|---|
| 1 | `if` / `for` / `while` in the pipeline body | No error; body is flattened, branch always taken, loop body runs once | Error (work item A) |
| 2 | `b = a * 2` in the pipeline body | No error; pipeline returns `()` | Error (A) |
| 3 | `amplify(img, gain=2.5)` | Kwarg silently ignored | Supported (B) |
| 4 | `blur(amplify(img))` | Returns `(None,)` | Supported (B) |
| 5 | `return amplify(img)` | `IndexError: list index out of range` | Supported (B) |
| 6 | Pipeline defined inside `main()` / any indented scope | `IndentationError: unexpected indent (<unknown>, line 1)` | Supported (A) |
| 7 | `np.abs(img)` / any `module.func(...)` | `KeyError: 'abs' not found… Probably misspelled`; only the attribute name is looked up in module globals | Supported (A) |
| 8 | `p(img, gian=2.0)`; `p(img, gain=99)` | Typo silently ignored; out-of-range silently clamped | Error / warning (C) |
| 9 | `@interactive(flip=True)`, `@interactive(gain=1.0)` | No widget, no warning | Checkbox / error (D) |
| 10 | Two filters that both declare a `gain` control | `ValueError: Duplicate control name` | Auto-disambiguated (E) |
| 11 | `p()` with a missing input | `Cannot set inputs to None when inputs_routing is defined` | Clear message (C) |
| 12 | `p.save("out.png")` | Logs "ndarray has no 'save' method" per image; only curves written | Images written (F) |
| 13 | `layout.style(..., colormap="viridis", vmin=0)` | Documented, but only `title`/`xlabel`/`ylabel` are read | Works or is not promised (G) |
| 14 | `pipe.load_tuning()` | Does not exist (method is `import_tuning`); quickstart, tips and the skill name it | Exists (H) |

## Ground rules

- Follow `CLAUDE.md`: venv python only, `ruff format` + `ruff check --fix` +
  full pytest before every commit, small focused commits with their tests, no
  `assert` for validation, no mutable defaults.
- Work only on this branch, in this checkout. Do not push, open a PR, merge,
  rebase other branches, bump the version or publish. Do not touch `master`
  or `feature/next-level`.
- Never open a real window: run with `QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg`.
- **Hard stop: 11:30 CET on 2026-11-14.** Check `date` regularly. By 11:15 stop
  starting new work: finish or revert the item in progress, leave the tree
  clean and the suite green, and fill in the Status section at the bottom.
- Work the items in the order below; each one is independently shippable, so
  a partial run still leaves a useful branch.
- Backward compatibility matters: every pipeline in `demo/`, `samples/`,
  `docs/` code blocks and `test/` must still build. Before tightening the
  parser, survey what those pipelines actually contain (docstrings, comments,
  `pass`, nested-list returns, `None` cells, filter instances, calls without
  assignment, no-input generator filters, attribute access such as
  `lib.filter(img)`) and keep all of it working. If the survey shows a
  currently-working pattern that this plan would reject, keep it working and
  note it in Status rather than breaking it.
- If a decision in this plan turns out to be wrong once you read the code,
  take the option that keeps existing user code working, and record what you
  did and why in Status.

## Work items

### A. Strict pipeline parser (rows 1, 2, 6, 7) — `core/graph.py`

The root cause is `get_call_graph`: it runs `ast.walk` over the whole tree and
keeps only the nodes it recognises, so everything else vanishes silently.

1. `textwrap.dedent` the source before `ast.parse` (row 6).
2. Iterate over the **top-level statements of the function body only** and
   validate each one. Allowed: a docstring, `pass`, an assignment whose value
   is a call (targets: a name or a flat tuple/list of names), a bare call
   expression, and a single final `return` of names / tuple / list / nested
   list / `None` cells (as today).
3. Anything else raises a new `PipelineSyntaxError` exported from
   `interactive_pipe`. Make it a `ValueError` subclass so existing
   `except ValueError` code keeps working. The message must contain the
   pipeline name, the file and absolute line number, the offending source
   line, and a hint specific to the construct, e.g. for `if`: "move the
   condition inside a filter"; for arithmetic: "wrap it in a filter function".
   Cover at least: `if`, `for`, `while`, `with`, `try`, arithmetic / any
   non-call expression on the right-hand side, augmented assignment,
   comprehensions, lambdas, more than one `return`, starred arguments.
4. Name resolution: resolve the called object from the pipeline function's
   real scope — closure variables (`inspect.getclosurevars`) then module
   globals — and resolve dotted calls (`np.abs`, `lib.blur`) by walking the
   attribute chain on the resolved root object, not by looking up the last
   attribute name (row 7). A pipeline and its filters defined inside `main()`
   must work. An unresolved name raises `PipelineSyntaxError` with a
   `difflib.get_close_matches` suggestion.
5. Keep the `FilterCore` instance path and the `_routing_by_indexes` path
   working.

### B. Widen what the pipeline body accepts (rows 3, 4, 5)

Do this only once A is committed and green.

1. **Literal keyword arguments** `amplify(img, gain=2.5)`: accept values that
   `ast.literal_eval` can evaluate. The value becomes that filter instance's
   parameter value; when a control is bound to the parameter it becomes that
   instance's control default (validated against the range, error if
   outside). A keyword that is not a parameter of the filter, or a
   non-literal value, raises `PipelineSyntaxError`. Beware that registered
   `Control` objects are shared through `Control._registry`: do not mutate the
   shared object in a way that leaks into another pipeline using the same
   filter — clone per instance, as the repeated-filter path already does.
2. **Nested calls** `blur(amplify(img))` and **`return f(x)`**: hoist the inner
   call into an auto-named intermediate variable, so the graph is the same as
   the two-line form. Pick a naming scheme that is deterministic, cannot
   collide with user variables, and reads well as an output title (it is shown
   in the GUI).
3. Non-literal positional arguments (`blur(img, 3)`, `blur(img * 2)`) stay
   errors, with a hint.

### C. Call-time validation (rows 8, 11) — `headless/pipeline.py`, `core/pipeline.py`, `graphical/gui.py`

1. Unknown keyword in `pipeline(img, gian=2.0)` raises `TypeError` listing the
   available parameter names with a close-match suggestion. Check the GUI
   `__call__` path too and keep the reserved names (`inputs`, `parameters`,
   `context`) working.
2. An out-of-range value is currently clamped without a word. Find where the
   clamp happens and make it audible: `logging.warning` naming the control,
   the value and the range. Keep the clamp (tuning files and sessions rely on
   it); do not turn it into an exception.
3. Wrong number of inputs raises
   `pipeline 'p' expects 1 input (img), got 0` (and the equivalent for the
   list and dict input forms).

### D. Scalar control shorthand (row 9) — `helper/keyword_args_analyzer.py`, `helper/control_abbreviation.py`

Applies to **decorator** keyword arguments only; plain defaults in the
function signature (`def f(img, flip=True)`) must keep meaning "no widget".

- `@interactive(flip=True)` → checkbox, same as `(True,)`.
- `@interactive(gain=1.0)` / a bare int or string → `ValueError` explaining
  that a range or a list of choices is needed, with the correct spelling.

### E. Duplicate control names across filters (row 10) — `headless/pipeline.py`

Two different filters each declaring `gain` is the normal case, not a mistake.

- When colliding controls are auto-named (`_auto_named`), disambiguate them
  instead of raising. Choose one scheme and apply it consistently with the
  existing repeated-filter suffix (`amount`, `amount_1`); the widget label
  must tell the user which filter it drives.
- Controls the user named explicitly (`name=...`) that collide still raise.
- Same sharing pitfall as B.1: the rename must not leak into another pipeline
  built from the same filter, and building the same pipeline twice (notebook
  re-run) must give the same names.
- Decide and document what `pipeline(img, gain=2.0)` does when several filters
  have a `gain` parameter (today it sets all of them), and how to target one.
- `test/test_control_registry.py` pins the current raise; update it.

### F. `HeadlessPipeline.save` writes images (row 12) — `headless/pipeline.py`

- numpy image outputs are saved through `Image`; 1D arrays, `Table` and `str`
  outputs are either saved in a sensible format or skipped with one clear
  warning — never a logged traceback for a supported output type.
- Return something useful (the list of written paths, or keep `path` if
  changing the return type breaks callers — check the GUI `save_images`).
- Document it in the quickstart headless section.

### G. `layout.style` heatmap options (row 13)

Preferred: honour `colormap`, `vmin`, `vmax` for 2D `(H, W)` arrays in **one**
shared place that every backend goes through when it fetches a cell for
display (start from `graphical/window.py`), using matplotlib colormaps
(matplotlib is a core dependency). Unknown style keys log a warning listing
the supported ones.

Fallback if no single hook exists and per-backend work would not fit the time
box: remove the unsupported keys from the `layout.style` docstring and docs,
and add the unknown-key warning. Say which path you took in Status.

### H. `load_tuning` (row 14)

Add `HeadlessPipeline.load_tuning` as an alias of `import_tuning` (three
places in the docs already promise it), with a test.

### I. Docs, skill, changelog

- `CLAUDE.md` and `.claude/skills/build-interactive-pipeline/SKILL.md`:
  replace "control flow breaks the AST parser" with what is now true (what is
  accepted, what raises `PipelineSyntaxError`), update the control table for
  `flip=True`, and fix the "Common errors" table.
- `docs/guide/decorators.md`, `docs/getting-started/quickstart.md`,
  `docs/guide/tips.md`, `docs/guide/layout.md` as needed; make sure the docs
  build is not broken if `mkdocs` is installed in the venv.
- `CHANGELOG.md`: an "Unreleased" entry listing each behaviour change, with
  the ones that can affect existing code called out (unknown kwargs now
  raise, stricter pipeline body, renamed colliding controls).

## Final verification

1. Full suite green, ruff clean, pyright not worse than baseline.
2. Re-run the 14 rows of the table as a script and paste the before/after
   one-liners into Status.
3. Build every pipeline in `demo/` and `samples/` headless (import with the
   GUI disabled, or construct via `HeadlessPipeline.from_function`) and
   confirm none raises.

## Status

Run started 2026-11-14 00:02 CET, autonomous (no reviewer reachable before
11:30). Baseline reproduced: `713 passed, 6 skipped`.

### Survey (before tightening the parser)

Recorded every pipeline body the parser sees while running the test suite
(246 parses) and while building every pipeline of `demo/` and `samples/`
headless (19 pipelines), and statically scanned the python blocks of `docs/`,
the root markdown files, the skill and `demo/multi_image.ipynb`. Patterns in
use: `x = f(a, b)`, `a, b = f(x)`, `f()` / `f(x)` without assignment,
no-input generators, docstrings, `...` as the whole body (docs/guide/tips.md),
`return name`, tuples, flat lists, nested-list (2D) returns, one literal
keyword argument (`split_horizontally(final, line=0.8)` in
test/test_recorder.py, ignored until B). No `pass`, attribute calls, filter
instances or `None` cells are used in existing pipelines, but they are kept
working and now tested. The only `if` found is the deliberately wrong example
in CLAUDE.md. Nothing in use is rejected by the strict parser.

### A. Strict pipeline parser — done (`ebc3029`)

- `PipelineSyntaxError(ValueError)` in `core/graph.py`, exported from
  `interactive_pipe`; message = pipeline name, file, absolute line, quoted
  source line, construct-specific hint. Attributes `pipeline_name`,
  `filename`, `lineno`, `source_line`, `hint`.
- Only top-level statements are visited; each is validated.
- Decisions beyond the plan:
  - Also accepted: `...` and string literals anywhere in the body (treated
    like comments — docs use `def my_pipeline(img): ...`), and annotated
    assignment `out: np.ndarray = f(img)`.
  - Source is `textwrap.dedent`-ed; if that fails (a multi-line string less
    indented than the body) it is parsed nested in a dummy block instead.
  - The pipeline function is `inspect.unwrap`-ed first, so a function already
    wrapped by `@interactive_pipeline(gui=...)` (functools.wraps) is analyzed in
    its own module/closure — `samples/decorated_pipeline_abbreviated.py`
    needed this once lookup moved from `inspect.getmodule` to `__globals__`.
  - Calling a Python builtin (`print(img)`) raises with "call it inside a
    filter" rather than being resolved as a filter.
  - Native callables (numpy ufuncs such as `np.abs`, C builtins) are wrapped
    into a positional-only filter: a filter receives every signature default
    as an explicit kwarg, which ufuncs reject (`cannot specify both
    'signature' and 'dtype'`).
  - Bug found on the way: `from_function` read `filt.controls` on filter
    instances, which only `EnhancedFilterCore` has; a plain `FilterCore`
    instance in a pipeline raised `AttributeError`. Now tolerated and tested.
  - Keyword arguments in filter calls are still ignored by this commit (they
    become supported in B); `**kwargs` and `*args` in calls raise.
- Tests: `test/test_pipeline_syntax.py`.

### B. Literal kwargs, nested calls, `return f(x)` — done (`4cfc0a0`)

- Literal keyword arguments (`ast.literal_eval`) set that filter instance's
  value. When a control is bound to the parameter, the instance gets a clone
  (`Control._clone_with_default`) whose default is the literal; the registered
  control is never mutated, so other pipelines using the filter and rebuilds
  are unaffected. Validation does not clamp: out of range, wrong type or not
  among the choices raises `PipelineSyntaxError` at the call's line.
  `RangeControl` validates the pair.
- Unknown keyword (with close-match suggestion), keyword naming an input,
  non-literal value (`gain=np.pi`, variables) and `**kw` raise.
- Nested calls and calls in the `return` (at any depth of the returned
  tuple/list) are hoisted into their own filter node, inner call first.
  Naming scheme: the call's own source, `ast.unparse(call)` — e.g.
  `amplify(img)`, `blur(amplify(img))`, `amplify(img, gain=2.0)`. It is
  deterministic, cannot collide with a user variable (not an identifier) and
  is a readable output title. An identical call repeated gets ` #2`, ` #3`.
- Positional literals (`blur(img, 3)`) raise with a hint naming the keyword
  it would map to (`radius=3`); expressions (`blur(img * 2)`) raise with the
  "wrap it in a filter" hint.
- Behaviour change to note: `split_horizontally(final, line=0.8)` in
  test/test_recorder.py is now honoured (it was ignored); the test filter
  does not use `line`, so its outputs are unchanged.
- Flaky: one full-suite run (of 7) at 00:15 died with a native crash dump
  (extension list showing PyQt6 / dearpygui); 6 reruns green, not
  reproduced. Probably a pre-existing GUI-backend flake, left for review.

### C. Call-time validation — done (`88de7f8`)

- Unknown keyword in `pipeline(img, gian=2.0)` raises `TypeError` listing the
  available parameter names, the reserved keywords and a close-match
  suggestion (`'gian' -> 'gain'`). It is checked before anything is changed
  (inputs, context, parameters), in both `HeadlessPipeline.__call__` and the
  GUI `__call__`.
- The GUI `__call__` now also accepts the reserved `inputs={...}` dict like
  the headless one (before, it would have been swallowed as an unknown kwarg).
- Out-of-range values are still clamped, in `Control.check_value` and
  `RangeControl.check_value` (the two clamp sites), now with
  `logging.warning("Control 'gain': value 99.0 is outside its range [0.0, 3.0], clamped to 3.0")`.
  Differences within 1e-9 of the span (slider float noise) do not warn.
  `TimeControl` is exempt: its timer keeps ticking past the end of its range
  and would warn on every frame.
- Wrong number of inputs: the message is produced by the `PipelineCore.inputs`
  setter, so the headless call, the GUI call and direct assignment all say
  `pipeline 'p' expects 1 input (img), got 0` (and `..., the inputs dict is
  missing mask (provided keys: img)` for the dict form). Decision: kept
  `ValueError` (the type raised today) rather than `TypeError`, so existing
  `except ValueError` code keeps working; the 4 tests in
  test/test_core_exceptions.py that pinned the old wording were updated.
- Tests: `test/test_call_validation.py`.

### D. Scalar control shorthand — done (`842e106`)

- Decorator keyword arguments only (`@interactive` and `@interact` share the
  code path): a bare bool is a checkbox, same as `(True,)`; a bare int, float
  or str raises `ValueError` that quotes the decorator, says a range / list of
  choices is needed, and spells the fix (`gain=(1.0, [0, 2.0])`,
  `mode=('dark', ['dark', 'other choice'])`) plus the signature-default
  alternative when no widget is wanted.
- Signature defaults (`def f(img, flip=True)`) still mean "no widget".
- Decision: a bare `None` in the decorator is left as it was (no widget, no
  error) — the plan did not cover it and it may be used to switch a control
  off programmatically.
- Tests: `test/test_decorator_scalar_shorthand.py`.

### E. Duplicate control names across filters — done (`6ecfa89`)

- Scheme: every auto-named control bound to a colliding parameter name is
  renamed `<filter instance>.<param>` — `amplify.gain`, `blend.gain`, and a
  repeated filter's clone in the same group becomes `amplify_1.gain`. The
  label says which filter it drives and reads exactly like the way to target
  it: `parameters={"amplify": {"gain": 2.0}}`. Repeats of one filter without
  any other collision keep today's `gain`, `gain_1` (no change for existing
  pipelines; none of demo/, samples/ or test/ had a collision since it
  raised).
- Explicitly named controls are never renamed; if two still collide, the
  existing `Duplicate control name` `ValueError` is raised. An explicit name
  colliding with an auto-named one: the auto-named one is renamed.
- "Auto-named" now also covers the tuple shorthand without a name
  (`(1.0, [0, 2])`) and the decorator bool shorthand: `control_from_tuple`
  marks them `_auto_named` (it used to pass `param_name` as an explicit name).
- Renamed controls are per-pipeline `_clone_unconnected` clones; the
  registered control keeps its name, other pipelines are unaffected and a
  rebuild gives the same names. Controls are now connected to their filter
  only after names are resolved.
- `pipeline(img, gain=2.0)` keeps setting `gain` in every filter that has it
  (documented in `parameters_from_keyword_args`); target one filter with
  `parameters={"blend": {"gain": 2.0}}`. Tested.
- `test/test_control_registry.py`: the pinned raise became the
  disambiguation test; added leak/rebuild, repeat+collision, explicit-name
  tests.

### F. `HeadlessPipeline.save` writes images — done (`e597258`, typing follow-up `ba06a22`)

- Without `data_wrapper_fn`, each output is written according to its type:
  numpy image (`(H, W)`, `(H, W, 1|3|4)`, float `[0, 1]` / uint8 / uint16 /
  bool) through `Image` (the given suffix if `.png/.jpg/.tif`, else `.png`;
  RGBA never to `.jpg`), 1D array -> `.csv`, other arrays -> `.npy`, `Image`,
  `Curve`, `SingleCurve`, `Table` -> their own `save` (given suffix when
  supported, else their default; `Table` falls back to `.pkl` without
  pandas), `str` -> `.txt`. Anything else is skipped with **one** warning
  listing the skipped outputs; no traceback for supported types.
  `data_wrapper_fn` keeps its old meaning.
- Returns the list of written files (tuning yaml excluded). Decision: the
  return type changed from `path` to `List[Path]`: no caller in src/, tests,
  demos or docs used the return value (the GUI `save_images` ignores it).
- Also fixed on the way: with a 2D output layout (`return [[a, b], [c]]`)
  nothing was saved, because output names were compared against the rows;
  output names are now flattened. File names are sanitised for
  `<>:"/\|?*` since hoisted names (`blur(amplify(img))`) can be file names.
- GUI `save_images` (key `w`) no longer forces `Image(...)` on every buffer
  (which logged a traceback for each curve/table); it uses the type dispatch.
- Documented in the quickstart headless section.
- Tests: `test/test_headless_save.py`.

### G. `layout.style` heatmap options — done, preferred path (`2e80148`)

- Single hook: `InteractivePipeWindow.refresh_display` (graphical/window.py),
  which the Qt, Dear PyGui, matplotlib, notebook and Gradio windows all go
  through, now passes each cell through `apply_display_style` before the
  backend's `convert_image`. A 2D `(H, W)` / `(H, W, 1)` numeric array whose
  style sets `colormap`, `vmin` or `vmax` is windowed to `[vmin, vmax]`
  (each defaulting to the data min/max, matplotlib semantics) and, with a
  colormap, converted to RGB with `matplotlib.colormaps`. Other contents are
  untouched. Qt still reports the raw value in its pixel readout (it keeps
  the raw outputs separately). Verified on Qt offscreen (pixel colour test).
- `layout.style` validates a colormap name (`ValueError` with a close-match
  suggestion, surfaced as a `FilterError`) and warns **once per key** for
  unknown keys, listing the supported ones (it runs every frame).
- Decision: `subtitle=` is used 7 times in demo/panel_demo.py,
  detached_panel_demo.py and grouped_controls_demo.py but was never shown by
  any backend. Rather than make those demos warn, it is now supported:
  appended to the title as `title · subtitle` (single line, works on every
  backend).
- `xlabel`/`ylabel` stay matplotlib-only; documented as such.
- Docs: new "Output style" section in docs/guide/layout.md.
- Tests: `test/test_layout_style_heatmap.py`.

### H. `load_tuning` — done (`1c89193`)

- `HeadlessPipeline.load_tuning(path)` delegates to `import_tuning`. Decision:
  `path` is required (the docs called `load_tuning()` with no argument,
  which with `import_tuning`'s optional path would only log a traceback);
  the quickstart, tips, samples/readme.md and the skill now pass the file.
- Test in `test/test_headless_save.py`.

### I. Docs, skill, changelog — done (`50164fb`)

- CLAUDE.md: the "control flow breaks the AST parser" section now states
  what is accepted and what raises `PipelineSyntaxError`.
- Skill: hard-rule section rewritten (accepted / rejected lists), checkbox row
  shows `flip=True`, bare-scalar error, colliding names, save, heatmap style,
  and a new "Common errors" table built from the actual messages.
- docs/guide/decorators.md: new "What a pipeline body may contain" section
  (with a real error message, checked against the code); the `interactive`
  and `interactive_pipeline` docstrings rendered there were updated too.
- docs/guide/controls.md: checkbox row, bare-value note, new "Same parameter
  name in several filters" section (renaming, kwargs vs `parameters=`,
  unknown kwargs, clamp warning).
- docs/getting-started/quickstart.md: pipeline-body warning box links the
  new section; bare-number note; `save` and `load_tuning(path)` (F, H).
- docs/guide/layout.md: "Output style" section (G). docs/guide/tips.md:
  only the `load_tuning(path)` fix was needed.
- CHANGELOG.md: "Unreleased" entry, with "Changes that can affect existing
  code" first.
- `mkdocs` is not installed in the venv, so the docs build was not run.

### Final verification

1. Full suite: `QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg ./venv/bin/python -m pytest test/ -q`
   -> `791 passed, 6 skipped` (baseline 713 + 78 new tests). `ruff format` /
   `ruff check` clean. pyright: 8 errors, same as the baseline (all
   pre-existing, in graphical/qt_control.py and graphical/dpg_panels.py).
2. The 14 rows, reproduced headless by a script run against the baseline
   source (`git archive 8213c59 src`, outside the repo) and against the
   branch:

   | # | Before (0.9.4) | After |
   |---|---|---|
   | 1 | `p1(img, flag=False)` -> mean 2: the `if` body ran anyway | `PipelineSyntaxError: pipeline 'p1', rows.py, line 65: `if` statements are not supported ...` |
   | 2 | `b = a * 2` -> returns `()` | `PipelineSyntaxError: ... line 72: arithmetic is not supported ...` |
   | 3 | `amplify(img, gain=2.5)` -> mean 1 (kwarg ignored) | mean 1.25 |
   | 4 | `blur(amplify(img))` -> `FilterError` (blur got `None`) | mean 2 |
   | 5 | `return amplify(img)` -> `IndexError: list index out of range` | mean 1 |
   | 6 | pipeline in `main()` -> `IndentationError: unexpected indent` | runs (mean 1.5) |
   | 7 | `np.abs(img)` -> `KeyError: "Function name 'abs' not found ..."` | runs (mean 0.5) |
   | 8 | `gian=2.0` ignored; `gain=99` silently clamped | `TypeError: ... unexpected keyword argument(s) 'gian' ... Did you mean 'gian' -> 'gain'?`; `gain=99` clamped + warning `Control 'gain': value 99.0 is outside its range [0.0, 3.0], clamped to 3.0` |
   | 9 | `flip=True` -> no control; `gain=1.0` -> no control | `flip=True` -> checkbox `flip`; `gain=1.0` -> `ValueError: @interactive(gain=1.0): a bare value cannot make a widget, a range is needed. Write gain=(1.0, [0, 2.0]) ...` |
   | 10 | `ValueError: Duplicate control name 'gain'` | controls `ctrl_gain.gain`, `other_gain.gain` |
   | 11 | `ValueError: Cannot set inputs to None when inputs_routing is defined` | `ValueError: pipeline 'p8' expects 1 input (img), got 0` |
   | 12 | `save('out.png')` -> only `out.yaml`, one logged traceback per image | `out.yaml`, `out_img.png`, `out_out.png`; returns the list |
   | 13 | `(H, W)` + `colormap='viridis'` displayed as `(4, 4)` gray | displayed as `(4, 4, 3)` viridis |
   | 14 | `hasattr(pipe, 'load_tuning')` = False | True |

3. Every pipeline in `demo/` (17) and `samples/` (2) builds headless
   (`HeadlessPipeline.from_function`, modules imported with
   `INTERACTIVE_PIPE_GUI=headless`): 19 built, 0 failed. samples/interact_sample
   and samples/object_oriented_pipeline_declarations.py contain no pipeline
   function. All rows have at least one regression test failing on the
   baseline (checked by running the new test files against the baseline
   source).

### Left for review

- Behaviour changes that can affect existing code are listed first in the
  CHANGELOG "Unreleased" entry; notably build-time `KeyError`/`TypeError`
  for unknown/non-callable names became `PipelineSyntaxError` (`ValueError`).
- Hoisted output names (`amplify(img)`) are also used as file names by
  `save` and as default titles; they are sanitised for Windows-forbidden
  characters only.
- test/test_core_exceptions.py `TestGraphExceptions` holds four empty
  placeholder tests (pre-existing); the real coverage is now in
  test/test_pipeline_syntax.py — they could be deleted.
- The one-off native crash seen in a full-suite run (see B) was not
  reproduced in later runs.
- Not done: docs build (mkdocs not installed in the venv).
