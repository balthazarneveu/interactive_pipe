# Plan: declare less — controls from type hints, and a second round of mistake-proofing

Branch: `feature/declare-less`, cut from `integration/next-level`.

## Why

Today every tunable parameter is written twice: once in the signature, once
in the decorator.

```python
@interactive(gain=(1.0, [0.0, 3.0]), mode=["dark", "light"], flip=(True,))
def f(img, gain=1.0, mode="dark", flip=True): ...
```

Coding agents and typed codebases already carry this information in the
signature. The goal is that a typed signature is enough, and that the
remaining runtime mistakes (inside filters and at their outputs) fail as
clearly as the build-time ones now do.

## Environment — read this first

This is a git worktree at `/home/bneveu/code/interactive_pipe_controls`. It has **no `venv/`**; the shared venv's
editable install points at another checkout. Replace `CLAUDE.md`'s
`./venv/bin/python` commands by:

```bash
cd /home/bneveu/code/interactive_pipe_controls
export PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg
PY=/home/bneveu/code/interactive_pipe/venv/bin/python
$PY -c "import interactive_pipe; print(interactive_pipe.__file__)"   # must print a path inside THIS worktree
$PY -m pytest test/ -q --tb=short        # baseline on this base: 867 passed, 6 skipped
$PY -m ruff format . && $PY -m ruff check --fix .
```

Check the printed path before trusting any test result. Do not `pip install`
into the shared venv. Do not read, edit or run git commands in any other
checkout (`/home/bneveu/code/interactive_pipe`, `..._snapshot`,
`..._integration`, and the sibling worktrees of the other agents).

## Context

Base branch `integration/next-level` already contains two pieces of work done
tonight; read their plans' Status sections first, they describe the code you
build on: `plan_fix_silent_failures.md` (strict pipeline parser,
`PipelineSyntaxError`, call validation, control renaming, `save`,
`layout.style` colormap) and `plan_agent_snapshot_loop.md`
(`snapshot` / `sweep` / `describe` on pipelines and single filters,
`INTERACTIVE_PIPE_SNAPSHOT`).

Two other agents work in parallel on sibling branches:
- `feature/scientific-outputs` owns `graphical/window.py`, every
  `graphical/*_gui.py` / `*_image.py` backend file, `headless/snapshot.py`,
  `data_objects/`, and `core/context.py` (`layout`).
- `feature/agent-packaging` owns `pyproject.toml`, `cli.py`, a new
  `__main__.py`, and the bulk rewrite of
  `.claude/skills/build-interactive-pipeline/SKILL.md` and the docs index.
You own `helper/keyword_args_analyzer.py`, `helper/control_abbreviation.py`,
`helper/filter_decorator.py`, `headless/control.py`, `core/engine.py`,
`core/filter.py` and `headless/explore.py`.
Stay out of the files they own. Keep edits to shared files (`CHANGELOG.md`,
`CLAUDE.md`, `SKILL.md`, `__init__.py`, `mkdocs.yml`, `readme.md`) to small
additive hunks in your own section, so the three branches merge cleanly.

## Ground rules

- Follow `CLAUDE.md` otherwise: ruff format + check and the full suite before
  every commit, small focused commits bundled with their tests, exceptions
  not `assert`, no mutable defaults.
- Work only on this branch in this worktree. Do not push, open a PR, merge,
  bump the version, publish, or comment on GitHub.
- Never open a real window (`QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg`).
- **Hard stop: 11:30 CET on 2026-11-14.** Check `date` regularly. By 11:15
  stop starting new work, leave the tree clean and the suite green, and fill
  in the Status section.
- Nobody can answer questions. When a decision here proves wrong once you
  read the code, pick the option that keeps existing user code working and
  record it in Status.
- Backward compatibility: every pipeline in `demo/`, `samples/`, docs code
  blocks and `test/` must keep working unchanged.
- Each item needs tests in new test files. Items are ordered by value and
  each is shippable alone.
- When you produce anything visual, render it with `pipeline.snapshot(...)`
  and look at the PNG with the Read tool before calling it done.

## Work items

### 1. Controls from annotations

Under `@interactive` (with or without other arguments), build controls from
the filter's own annotations. Only constructs that are an explicit opt-in
create a widget; a plain `gain: float = 1.0` or `flip: bool = False` must keep
meaning "no widget", as today.

- `Annotated[float, (0.0, 3.0)]`, `Annotated[int, (1, 15)]`, optional step as
  third element, optional label string and group as further metadata — i.e.
  the metadata is what the existing tuple shorthand accepts after the
  default; the default comes from the signature.
- `Annotated[<type>, Control(...)]` and subclasses (`KeyboardControl`,
  `RangeControl`, `CircularControl`, `TextPrompt`, `TimeControl`). Mind the
  shared-registry pitfall documented in `plan_fix_silent_failures.md`: one
  `Control` instance in an annotation must not end up shared between
  functions or mutated across pipelines.
- `Literal["dark", "light"]` → dropdown, default from the signature (first
  choice when there is none). `Annotated[bool, ...]` with a label → checkbox.
  Decide whether a bare `Literal` under `@interactive()` is opt-in enough or
  needs `Annotated`; existing code with `Literal` hints must not suddenly
  grow widgets it did not ask for unless you judge that harmless — record the
  decision.
- `Enum` parameters: a dropdown over the members, passing the member (not its
  name) to the filter. Check each backend's dropdown handles non-string
  choices or map through names.
- Precedence: decorator argument > annotation > nothing. A parameter declared
  both ways is not an error; the decorator wins.
- `from __future__ import annotations` (string annotations) must work: use
  `typing.get_type_hints(func, include_extras=True)` and fall back cleanly
  when a hint cannot be resolved. Python 3.9 is supported: `Annotated` comes
  from `typing` there, no `X | Y` syntax in the library.
- A default outside the annotated range, or a default whose type contradicts
  the hint, raises at decoration with the function name, the parameter and
  the fix.
- `pipeline.describe()` and the filter-level `.describe()` must report these
  controls like any other.
- Bare `@interactive` (no parentheses) should work if it does not already.

### 2. Runtime mistakes inside filters and at outputs

Reproduce each of these headless first, keep the ones that fail badly, and
fix them. For each: either the intended behaviour, or an error naming the
filter, the line when there is one, and the fix. Add to this list anything
else you hit while probing — spend real time probing, the list is a seed.

- A filter returns the wrong number of values for the pipeline's unpacking
  (`a, b = f(x)` where `f` returns one array, and the reverse).
- A filter returns `None` (forgot the `return`).
- A filter returns a type no backend can display (dict, list of arrays,
  torch tensor, PIL image, matplotlib axes): what does headless do, what do
  `snapshot` and the GUIs do? Unsupported outputs should say which types are
  supported. Do not add support for new output types — the
  scientific-outputs branch owns that.
- Images with surprising content: `uint8`, `uint16`, float outside `[0, 1]`,
  NaN/inf, `(H, W, 1)`, `(H, W, 4)`, `(1, H, W)` channel-first, `bool`
  masks, empty arrays. Tabulate what each backend path does (code reading is
  enough for the GUI ones) and fix the cases that crash or mislead. Report
  what you did not fix.
- An `int` default with a float range and the reverse; a default outside the
  range; a step larger than the range; an empty choice list; a choice
  default not in the list. Check the messages name the function and the
  parameter.
- Calling a `@interactive` filter directly with a positional value for a
  controlled parameter, or with an unknown keyword.
- A filter that reads `context["key"]` before any filter wrote it:
  the `KeyError` should say which keys exist and that order matters.
- A filter name in the pipeline body that shadows an input name, or the same
  variable assigned twice (`a = f(img); a = g(a)`) — verify the graph is
  right, including with `cache=True` and `cache="graph"`.
- An exception raised inside a filter while running under each cache mode:
  the next run must recompute, not serve a stale result.

### 3. Small fixes left over from the merge

- `sweep` caption: sweeping `**{"amplify.gain": [...]}` in a pipeline where
  another filter also has a `gain` parameter drops that other filter's `gain`
  from the caption (it prints `blend: flip=True` instead of
  `blend: gain=0.5, flip=True`). Only the swept parameter should be omitted.
- `test/test_core_exceptions.py::TestGraphExceptions` holds four empty
  placeholder tests; delete them.
- Read `headless/explore.py`'s own parameter-name validation and
  `HeadlessPipeline.__call__`'s (added on the other branch): they should
  accept the same spellings (`gain`, a control name such as `amplify.gain`,
  `"filter.param"`) and produce the same style of message. Unify them behind
  one helper.

### 4. Docs

- `docs/guide/controls.md`: a section on annotation-declared controls next to
  the decorator form, saying which to prefer when.
- Add your own short section to `SKILL.md` and `CHANGELOG.md` ("Unreleased").

## Status

Agent run of 2026-11-14, started 02:02 CET (autonomous, nobody reachable
before 11:30). Environment check: the shared interpreter imports
`interactive_pipe` from this worktree's `src/`; baseline `867 passed, 6 skipped`
reproduced before any change.

### 1. Controls from annotations — done

New module `helper/annotation_controls.py`, wired in
`keyword_args_analyzer.analyze_filter_controls` and the `@interactive` wrapper.
Decisions:
- Opt-ins that make a widget: `Annotated[T, (min, max[, step]), label?, group?]`,
  `Annotated[str, [choices...]]`, `Annotated[bool, "label"(, group)]`,
  `Annotated[T, Control(...)]` (any subclass), `Annotated[Tuple[float, float],
  (min, max)]` (range slider, an extra), `Literal[...]` and `Enum` hints.
  Plain `float` / `bool` / `str` hints, foreign `Annotated` metadata and
  `Optional[...]` make no widget.
- **Bare `Literal` / `Enum` under `@interactive` are opt-in enough** (no
  `Annotated` needed): they carry the full choice set, the default is unchanged
  so outputs are unchanged, and only `@interactive` filters are concerned (plain
  functions in a pipeline never get widgets). No `Literal` / `Enum` hint exists
  in `demo/`, `samples/`, docs or tests.
- `Annotated[float, "some doc"]` (a label but no range) makes no widget and logs
  a warning: a hard error would break code using `Annotated` for documentation.
- Enum and non-string `Literal` (`Literal[3, 5]`) become a
  `MappedChoiceControl` (new, `headless/control.py`): a plain *string* dropdown
  over labels (member names / `str(value)`), so no backend change was needed
  (all backends key dropdowns on `_type is str`; checked by reading
  qt/mpl/nb/dpg/gradio control factories, plus a Qt offscreen test). The
  `@interactive` wrapper hands the filter the member / value; the control
  accepts both labels and values (`pipeline(img, style=Style.GLOSSY)` or
  `style="GLOSSY"`), tuning files store the label.
- A `Control` found in an annotation is cloned per function (a type alias
  shared by several filters must not share one Control); when the signature
  default differs from the Control's default, the signature default wins and is
  validated against the control (out of range raises).
- Missing signature default: first choice for `Literal`/`Enum`, midpoint for a
  range (like the `[min, max]` ultra-short form), `False` for a checkbox, full
  span for a range slider. The wrapper's `__signature__` gets the filled
  default, so the parameter is a control, not a pipeline input. If inputs
  without default follow it, decoration raises with the fix.
- int default for a float hint is coerced (numeric tower); a float default for
  an int hint, a bool for a number, a non-choice default, an out-of-range
  default, an empty range, a step <= 0 or larger than the range, label clashes
  raise `ValueError`/`TypeError` at decoration with
  `@interactive filter '<qualname>' (<file>:<line>), parameter '<p>': <problem>. Fix: <fix>`.
- String annotations: `typing.get_type_hints(include_extras=True)` with the
  locals of the frame applying the decorator (aliases defined inside `main()`
  resolve); if that fails, each hint is evaluated alone and unresolvable ones
  are skipped (warning when the text mentions `Annotated` / `Literal`).
- Precedence: decorator argument > annotation > signature-default shorthand.
- Bare `@interactive` (no parentheses) now works (it returned a broken wrapper).
- `filter_from_function` / `@interact` read annotations too.
- Also in this commit (same wrapper rewrite, tested in
  `test/test_filter_direct_call.py`): a positional value for a controlled
  parameter wins over the control (it raised `multiple values for argument`),
  and bad direct calls raise `TypeError` naming the filter, with a close-match
  suggestion for an unknown keyword.
- Tests: `test/test_annotation_controls.py`, `test/test_filter_direct_call.py`.
- Follow-up `fd39edf`: a `None` default (`mode: Literal["a", "b"] = None`,
  usually "automatic") or an `Optional[...]` hint makes no widget. It raised on
  Python >= 3.11 but was ignored on 3.9/3.10 (`get_type_hints` wraps it in
  `Optional` there); an explicit `Annotated` range/label with `None` logs a
  warning.
- Built the real Qt and matplotlib windows offscreen with every annotation
  kind (slider, labelled int slider in a group, checkbox, Literal str / int,
  Enum, range, circular, keyboard, text prompt): widgets are created, and the
  Qt dropdowns hand the filter `Style.GLOSSY` and the int `3`.
- Observed, not changed: registered controls are shared by every pipeline built
  from the same filter, so a value tuned in one pipeline is the starting value
  of the next one (pre-existing, same with decorator controls).

### 2. Runtime mistakes inside filters and at outputs — done

Commits `9b7bbe4` (filter results, context), `e484c80` (control declarations),
`ef4bc7e` (output checker), `2a25644` (call-time values, partial, exec).
Probes were run headless (`HeadlessPipeline`, every cache mode) and against
the Qt and matplotlib backends offscreen (window refresh); dpg by reading
`dpg_image.numpy_to_rgba`, gradio only by its `convert_image` (clip to
[0, 1] then uint8), nb not checked.

Seed list:
- **Wrong unpacking.** `a, b = f(x)` with one value already raised, but
  pointed at a framework line. `a = f(x)` with `f` returning two values, and
  `a, b = f(x)` with three, **silently kept the first value(s)**. Now a
  `FilterOutputError(ValueError)` (wrapped in `FilterError`) names the filter,
  the pipeline, file, line and source of the call, and the fix
  (`out0, out1 = f(x)`, or `return (values,)` to keep a tuple as one value).
  Decision: the strict check applies to filters built from a pipeline body
  (they carry `call_location`); `FilterCore` lists assembled by hand, the
  `@interact` dry run and single-filter entry points keep the lenient
  behaviour. All demos/samples still run (checked with
  `INTERACTIVE_PIPE_SNAPSHOT` on every script of `demo/` and `samples/`).
- **`None` returned.** Raised only when the function has no `return <value>`
  at all (AST check, cached per code object) and the pipeline assigns its
  result: an explicit/conditional `return None` stays allowed (can be an
  intentionally empty cell), and unassigned calls `f(img)` are untouched.
- **Context read before write.** `FilterError` gets a hint (detected from the
  traceback going through `core/context.py`, which I did not edit since the
  scientific-outputs branch owns it): key name, keys present now, "filters run
  in the order of the pipeline body", `context.get(key, default)` /
  `pipeline(..., context={...})`, and the later filters whose source mentions
  the key. Works in every cache mode, for `context["k"]` and `context.k`.
- **Shadowing / reassignment** (`img = f(img)`, `a = f(img); a = g(a)`) and
  **rerun after an exception**: already correct in `False`, `True` and
  `"graph"` modes; regression tests added, no change.
- **Control declarations.** int default + float range (and reverse) gives a
  float slider, as documented: kept. Fixed: step <= 0 and step larger than the
  range were accepted (now `ValueError` in `Control`), `min >= max` gave
  "value_default must be within", a 4-element range dropped values, and the
  shorthand reported the ultra-short fallback's error ("max parameter should
  be numerical too", "wrong abbreviation") instead of the real one. Every
  decorator error is now prefixed `@interactive filter '<f>', parameter '<p>':`
  and the typo error suggests the closest parameter. Also fixed:
  re-decorating a function with the same qualname (notebook re-run) kept
  controls removed from the declaration in the registry.
- **Direct calls.** Positional value for a controlled parameter now wins
  (raised "multiple values"); unknown keyword names the filter with a
  suggestion (in item 1's commit).

Found while probing (added to the list):
- `pipeline(img, gain=np.float32(2.0))` (any numpy scalar) raised
  `TypeError: Expected <class 'float'>`: numpy scalars are now plain values.
- `gain=True` on a float slider was taken as 1.0: now `TypeError`.
- Control type errors did not name the control: now
  `control 'gain' expects float, got str '2'`.
- `functools.partial(filter, gain=2.0)` used as a filter crashed with
  `AttributeError: __qualname__` (registry key): now works (no widget, the
  partial's values are used).
- A pipeline defined with `exec` / `python -c` raised a bare `OSError: could
  not get source code`: now `PipelineSyntaxError` with the reason and the fix
  (small hunk in `core/graph.py`, not owned by any branch).
- `parameters={"amp": {"gian": 2}}` failed at run time as a `FilterError`: now
  validated at call time (item 3 commit).

**Unsupported / surprising outputs.** Detection only (the scientific-outputs
branch owns output support): new `headless/output_check.py`; `snapshot()` and
`sweep()` log one warning per problematic output, with the fix and the list
of displayable types. Behaviour per path (before -> what this branch does):

| Output | headless | snapshot (renderer) | Qt | matplotlib | dpg / gradio (code reading) | this branch |
|---|---|---|---|---|---|---|
| dict, list, int, PIL, matplotlib Axes, torch | returned as is | grey "cannot be displayed" box | nothing drawn | nothing drawn | not drawn | snapshot/sweep warn "not a displayable type" + fix |
| `uint8` / `uint16` image | ok | uint8 shown 0-255, uint16 white | clipped to [0,1] -> **white** | clipped -> white | clipped -> white | warn "misleading", fix `/ 255.0` |
| float far outside [0, 1] | ok | clipped | clipped | clipped | clipped | warn when < -1 or > 2 (mild saturation stays quiet) |
| NaN / inf | ok | black / white pixels | same (+ numpy cast warning) | same | same | warn, fix `np.nan_to_num` |
| `(H, W, 1)` | ok | shown gray | **ValueError** "Expected 3-channel image" (no output named) | ok | dpg NotImplementedError, gradio not checked | warn, fix `img[..., 0]` |
| `(H, W, 4)` | ok | ok | **ValueError** | ok | dpg ok, gradio not checked | warn (Qt), fix `img[..., :3]` |
| `(3, H, W)`, `(1, H, W)` | ok | placeholder | **ValueError** | **TypeError** Invalid shape | NotImplementedError | warn, fix `np.moveaxis` |
| `(H, W, 2)`, 4D batch | ok | placeholder | **ValueError / NotImplementedError** | **TypeError** | NotImplementedError | warn |
| bool mask | ok | ok | ok | ok | ok | nothing to do |
| empty array | ok | placeholder | nothing drawn | singular-limits warning | - | warn |
| complex / object | ok | white / placeholder | not probed | not probed | not checked | warn |

Not fixed (left to the scientific-outputs branch, which owns the backends):
the Qt / matplotlib / dpg crashes above, which name neither the output nor the
filter, and integer images clipped to white in the GUIs. A suggested fix is to
call `output_check.output_problem(value)` in `window.py::refresh_display`
before `convert_image` and show the message in the cell. After the merge,
`SUPPORTED_OUTPUTS` / `output_problem` must learn the new output types that
branch adds, or snapshot will warn about them.

### 3. Small fixes left over from the merge — done

- Sweep caption (`c3857d5`): the caption now excludes only the swept
  `(filter, parameter)` pairs; sweeping a bare name still hides it everywhere.
- Placeholder tests deleted (`6bc8419`).
- One resolver (`eb39edd`): `explore.resolve_names` / `unknown_names_error`
  are used by `pipeline(...)` (`HeadlessPipeline.parameters_from_keyword_args`,
  hence the GUI `__call__` too), `snapshot`, `sweep` and the filter entry
  points. Same spellings everywhere (parameter name, control name such as
  `amplify.gain` / `Exposure` / `gain_1`, `"filter.param"`), same message
  (`<caller> got unexpected keyword argument(s) 'gian'. Available parameters:
  ... Did you mean 'gian' -> 'gain'? ...`). Decision: kept the pipeline
  call's wording (quoted in SKILL.md's error table) rather than snapshot's
  `unknown parameter`; two tests pinning the old snapshot/sweep wording were
  updated. `parameters={...}` is validated at call time with the same style.

### 4. Docs — done (`8ee11ae`, `a2fb126`)

- `docs/guide/controls.md`: "Controls from type annotations" section next to
  the decorator styles, with the rules and "which to prefer when" (annotations
  for new typed code; decorator for functions that must not import
  interactive_pipe, functions you do not own, prototyping). Its code block was
  executed with a real body and rendered with `snapshot` / `sweep` (PNG
  checked). The same-name section mentions `pipe(img, **{"blend.gain": 2.0})`.
- `SKILL.md`: own section "Controls from type annotations" (with the new
  runtime error messages, no edit to the shared error table);
  `CHANGELOG.md`: own "Declare less" subsection at the end of "Unreleased",
  changes that can affect existing code first. CLAUDE.md not changed.
- `mkdocs` is not installed in the shared venv: the site build was not run.

### Extra checks

- **Python 3.9**: a throwaway venv on `/Data/venvs/ip39-declare-less`
  (numpy, matplotlib, Pillow, PyYAML, pytest; no Qt). All new test files pass
  (Qt test skipped). Full suite on 3.9: 7 failures, all environmental (no
  opencv, no Qt / ipywidgets), and the same 7 fail on the base commit
  (`git archive c515a6a`), so none come from this branch.
- **Docs code blocks**: every python block of `docs/`, `readme.md` and the
  skill mentioning `interactive` was executed under
  `INTERACTIVE_PIPE_SNAPSHOT` (fragments re-run with an import header). No
  error from this branch; fragments only miss names defined elsewhere. One
  pre-existing crash found and fixed (`7ed2eeb`): a pipeline calling no filter
  (`def my_pipeline(img): ...` in tips.md) raised `IndexError`, now a
  `ValueError` naming the pipeline (`test_edge_cases.py` pinned the
  `IndexError`; updated).
- **Demos / samples**: all 17 demos and 3 samples run unmodified under
  `INTERACTIVE_PIPE_SNAPSHOT` after the stricter output checks.
