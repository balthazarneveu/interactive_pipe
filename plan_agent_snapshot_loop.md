# Plan: a see-the-result loop — snapshot, sweep, describe (pipelines and single filters)

Branch: `feature/agent-snapshot-loop`, cut from `feature/next-level` at `8213c59`.
Checkout: the git worktree `/home/bneveu/code/interactive_pipe_snapshot`.
Baseline: `713 passed, 6 skipped`.

## Why

A coding agent (or a user over SSH, or CI) cannot look at a Qt window. Headless
mode already runs the pipeline and hands back raw arrays, `Curve` and `Table`
objects, but there is no way to get **what the GUI would have shown** — the
grid, the titles set through `layout.style`, the plots — as a file that can be
read back. Today `HeadlessPipeline.save` even fails on numpy images.

This work adds that on top of headless mode: headless is the engine, the
snapshot is its display. It also covers GitHub issue #21 ("@interactive
decorator could return a filter instance… even a simple filter should be
testable with a graphical interface"): a single decorated filter gets the same
entry points as a pipeline.

Target usage:

```python
@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img, gain=1.0): ...


@interactive_pipeline()  # any gui= value
def pipe(img):
    amplified = amplify(img)
    histo = histogram(amplified)
    return amplified, histo


pipe.describe()  # controls, ranges, outputs
pipe.snapshot("out.png", img, gain=2.0)  # the whole grid in one PNG
pipe.sweep("sweep.png", img, gain=[0.5, 1, 2])  # contact sheet

amplify.snapshot("amp.png", img, gain=2.0)  # same, for one filter
amplify.sweep("amp_sweep.png", img, gain=[0.5, 1, 2])
amplify.describe()
amplify.interact(img)  # open the GUI on this filter
```

## Environment — read this first

This worktree has **no `venv/`**, and the shared venv's editable install points
at the *other* checkout (`/home/bneveu/code/interactive_pipe`), where another
agent is working on a different branch. So `CLAUDE.md`'s `./venv/bin/python`
commands must be replaced by:

```bash
cd /home/bneveu/code/interactive_pipe_snapshot
export PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg
PY=/home/bneveu/code/interactive_pipe/venv/bin/python
$PY -c "import interactive_pipe; print(interactive_pipe.__file__)"   # must print a path inside THIS worktree
$PY -m pytest test/ -q --tb=short
$PY -m ruff format . && $PY -m ruff check --fix .
```

Check the printed path before trusting any test result. Do not `pip install`
anything into the shared venv, and do not read, edit or run git commands in
`/home/bneveu/code/interactive_pipe`.

## Ground rules

- Otherwise follow `CLAUDE.md`: ruff format + check and the full suite before
  every commit, small focused commits bundled with their tests, exceptions not
  `assert`, no mutable defaults.
- Work only on this branch in this worktree. Do not push, open a PR, merge,
  bump the version, publish, or comment on the GitHub issue.
- Never open a real window (`QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg`).
- **Hard stop: 11:30 CET on 2026-11-14.** Check `date` regularly. By 11:15
  stop starting new work: finish or revert the item in progress, leave the
  tree clean and the suite green, and fill in the Status section.
- Items are ordered by value and each is shippable alone.
- **Stay out of the other branch's way.** `fix/silent-pipeline-failures` is
  rewriting, in parallel: `core/graph.py` (pipeline parser),
  `HeadlessPipeline.__call__` / `.save` / input validation, the duplicate
  control-name logic in `HeadlessPipeline.from_function`,
  `helper/keyword_args_analyzer.py`, `helper/control_abbreviation.py`, and the
  `layout.style` colormap handling. Do not modify those. Put the new code in
  new modules and keep edits to existing files to small additive hunks (new
  methods at the end of a class, new attributes on a wrapper, new exports) so
  the two branches merge cleanly. In `CHANGELOG.md`, `CLAUDE.md` and the
  skill, add your own section rather than editing existing paragraphs.
- If a decision here proves wrong once you read the code, pick the option that
  keeps existing user code working and record it in Status.

## Work items

### 1. Renderer — new module `headless/snapshot.py`

A pure-headless function that turns one run result into a PNG.

- Use `matplotlib.figure.Figure` + `FigureCanvasAgg` directly, never
  `pyplot`, so it has no global state, does not depend on the active
  matplotlib backend and is safe next to a running Qt/DPG GUI.
- Respect the pipeline's output layout: flat tuple → one row; 2D layout →
  grid; `None` cells stay empty.
- One cell per output, by kind (reuse `graphical/window.py::display_kind`):
  image arrays (`imshow`, no axes, float in [0, 1] or uint8, grayscale 2D),
  1D arrays (line plot), `Curve` (reuse its own `create_plot(ax)` so it looks
  like the GUI), `Table` (reuse `create_table(ax)`), `str` (text cell).
  An unsupported type renders a labelled placeholder cell, not an exception.
- Cell titles: the `layout.style(name, title=...)` value when set, otherwise
  the output variable name — same rule as the GUI (`graphical/window.py`).
  Read styles from `pipeline.framework_state.output_styles` after the run.
- Options: `figsize` / `dpi` with sensible automatic defaults derived from
  the grid shape and image aspect ratios, and an optional figure title.
  Optionally print the parameter values used as a small caption, so a
  snapshot is self-describing (on by default; `caption=False` turns it off).
- Look at the mpl backend (`graphical/mpl_gui.py`, `mpl_window.py`) before
  writing new drawing code and share helpers where that is a small change.

### 2. `HeadlessPipeline.snapshot`

`snapshot(path, *inputs, inputs=None, output=None, **params) -> Path`

- Runs the pipeline with the given inputs and parameter overrides, renders,
  writes the PNG (create parent directories) and returns the path.
- Inputs may be omitted when the pipeline takes none or has already been
  called (reuse the last inputs); otherwise raise a message saying which
  inputs are expected.
- **Stateless with respect to tuning:** parameter overrides apply to this
  call only; the pipeline's parameters and control values are restored
  afterwards, also when the run raises. (`export_animation` in
  `headless/animation.py` is the existing example of this pattern.)
- Parameter names are validated here, in the new code: an unknown name raises
  `TypeError` listing the available names with a `difflib` close match. Do not
  change `__call__` for this — the other branch owns that.
- `output=` selects a subset (name, index, or list of them) to render.
- With `path=None`, return the rendered image as an `(H, W, 3)` uint8 array
  instead of writing a file (useful in notebooks and tests).
- A `FilterError` during the run propagates unchanged.

### 3. `HeadlessPipeline.sweep`

`sweep(path, *inputs, output=None, **{param: [values]}) -> Path`

- One swept parameter → one row (or column) of snapshots, each labelled
  `param=value`. Two swept parameters → a 2D grid with row and column labels.
  More than two → `ValueError` with a hint.
- Scalar keyword values are fixed overrides applied to every cell; list /
  tuple / numpy-array values are the swept axes. `RangeControl` values are
  themselves tuples: decide how to disambiguate and document it.
- `output=` picks which output is shown per cell; default is the first image
  output, or the whole grid when the pipeline has a single output.
- Same statelessness and name validation as `snapshot`.
- Add a convenience for "sweep this control over its declared range":
  e.g. `gain=5` meaning five evenly spaced values is ambiguous with a fixed
  override, so use an explicit spelling such as `steps={"gain": 5}` or a
  small helper — pick one and document it.

### 4. `HeadlessPipeline.describe`

`describe() -> dict`, JSON-serialisable (test it with `json.dumps`):

- pipeline name, input names, output layout;
- filters in execution order with their input and output variable names and
  current parameter values;
- controls: name, owning filter, parameter name, kind (slider / checkbox /
  dropdown / range / text / time / keyboard), default, current value, range or
  choices, step, group/panel, key bindings and tooltip when present.

Also give `HeadlessPipeline` a short `help()`-style text rendering of the same
data (or improve `__repr__` additively) so a terminal user gets a readable
summary. numpy scalars and `Panel` objects must be converted to plain types.

### 5. Reachable from any decorated pipeline

`@interactive_pipeline(gui="qt")` returns a plain function with a `.pipeline`
attribute (the GUI object), not a `HeadlessPipeline`. Attach `snapshot`,
`sweep` and `describe` to that function too (delegating to the underlying
headless pipeline, without opening a window), and add them to
`InteractivePipeGUI` if that is a small additive change. The point: the same
script works with any `gui=` value, and an agent can add one `pipe.snapshot`
line to a user's GUI script without touching the decorator.

### 6. Single-filter entry points (GitHub issue #21)

The issue asks for `@interactive` to return a filter instance so that a lone
filter is easy to run and test. Keep returning a plain function (it stays
picklable, keeps `functools.wraps` metadata, and `test/` relies on it), and
attach the entry points to the wrapper instead:

- `f.snapshot(path, *inputs, **params)`, `f.sweep(...)`, `f.describe()` — build
  a one-filter pipeline internally (`filter_from_function` /
  `EnhancedFilterCore` in `helper/filter_decorator.py` already do this for
  `@interact`) and reuse items 2–4. Output names: reuse the dry-run deduction
  that `run_gui` does, so multi-output filters work.
- `f.interact(*inputs, gui="auto", **gui_kwargs)` — open the GUI on this one
  filter; this is `@interact` made available after the fact.
- Building the one-filter pipeline must not disturb the filter's use in a
  real pipeline afterwards: registered `Control` objects are shared through
  `Control._registry`, so do not leave them connected to the throwaway
  filter, and do not leave control values changed.
- The issue's original bug (`get_curve_2(frequency=5.)` ignoring the keyword)
  is already fixed on this base; add a regression test for it.

### 7. Snapshot without editing the script (stretch)

Environment variable `INTERACTIVE_PIPE_SNAPSHOT=<path.png>`: when set, calling
a GUI-decorated pipeline renders the snapshot to that path and returns the
results instead of opening a window. This lets an agent run a user's
unmodified demo and look at the result. Put the environment parsing in
`cli.py` next to the existing `INTERACTIVE_PIPE_GUI` helpers, and document the
precedence. Verify it on three or four scripts from `demo/`. Skip this item if
time is short; say so in Status.

### 8. Docs, skill, changelog

- New guide page `docs/guide/snapshots.md` (add it to the `mkdocs.yml` nav):
  the usage block above, one real rendered snapshot and one sweep image
  generated by your code and committed under `docs/images/`, and a short
  "working with a coding agent" section describing the loop: `describe()` →
  `snapshot()` → read the PNG → adjust → `sweep()`.
- Link it from the quickstart headless section and the readme "Learn more"
  list.
- `.claude/skills/build-interactive-pipeline/SKILL.md`: add a section
  "Check your work without a display" with the same loop. This is the most
  important doc change — it is what other agents will read.
- `CHANGELOG.md`: an "Unreleased" entry.
- Export what should be public from `interactive_pipe/__init__.py`.

## Quality bar

- Tests for every item in new test files: PNG exists, has the expected grid
  proportions, is not blank, cells differ when parameters differ; parameters
  are restored after `snapshot` / `sweep`, including after an exception;
  `describe()` round-trips through `json.dumps`; unknown parameter names
  raise; filter-level calls leave the filter usable in a pipeline.
- **Look at your own output.** After implementing the renderer, generate
  snapshots and sweeps for several demos (`demo/image_analysis_demo.py`,
  `demo/table_demo.py`, `demo/independent_curve_image_demo.py`, a 2D-layout
  one) and open the PNGs with the Read tool. Fix what looks wrong: clipped
  titles, squashed images, unreadable tables, overlapping labels, wasted
  whitespace. The feature is only worth having if the image is good enough to
  debug from.
- Full suite green, ruff clean, pyright not worse than baseline.

## Status

Agent run of 2026-11-14 (started 00:08 CET). Environment check: the shared
interpreter imports `interactive_pipe` from this worktree's `src/`; baseline
`713 passed, 6 skipped` confirmed before any change.

### 1. Renderer — done

New module `headless/snapshot.py` (Figure + FigureCanvasAgg, no pyplot).
Decisions:
- Tables are drawn by the renderer itself (`ax.table` with a bbox filling the
  cell, natural row height, top-aligned, bold header, truncated after 30 rows
  with a "... N more rows" line) instead of `Table.create_table`: with
  `loc="center"` + `scale(1, 2)` the GUI helper overflows its axes and the
  table title collided with the neighbouring cells in `demo/table_demo.py`.
  `Curve.create_plot(ax)` is reused as planned.
- uint8 images are shown on a 0-255 scale (the GUIs clip every array to
  [0, 1], which turns uint8 images almost binary); floats are clipped to
  [0, 1], grayscale uses a gray colormap, small images use nearest
  interpolation so test patterns stay crisp.
- A Curve's own title wins over the `layout.style` title (same rule as the mpl
  backend); a style without `title` falls back to the variable name.
- `layout.style(colormap=...)` is not applied: no backend implements it on this
  base and the other branch owns that handling.
- Automatic dpi shows the largest image near native size (80-150 dpi); the
  figure is scaled down when wider than 22 in.

