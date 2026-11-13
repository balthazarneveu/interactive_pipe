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

### C. Call-time validation — done

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
