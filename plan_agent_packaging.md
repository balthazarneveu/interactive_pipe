# Plan: make the library easy for coding agents to pick up — packaged skill, CLI, docs

Branch: `feature/agent-packaging`, cut from `integration/next-level`.

## Why

An agent working in *someone else's* repository only has
`pip install interactive-pipe`. Today the agent skill lives in this
repository's `.claude/` folder and is not in the wheel, there is no command
line entry point, and the skill predates tonight's changes. The goal: after
`pip install`, one command gives an agent accurate instructions, and one
command lets it look at what a script displays.

## Environment — read this first

This is a git worktree at `/home/bneveu/code/interactive_pipe_packaging`. It has **no `venv/`**; the shared venv's
editable install points at another checkout. Replace `CLAUDE.md`'s
`./venv/bin/python` commands by:

```bash
cd /home/bneveu/code/interactive_pipe_packaging
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
- `feature/declare-less` owns `helper/keyword_args_analyzer.py`,
  `helper/control_abbreviation.py`, `helper/filter_decorator.py`,
  `headless/control.py`, `core/engine.py`, `core/filter.py`,
  `headless/explore.py`. It is adding controls declared through
  `typing.Annotated` / `Literal` annotations.
- `feature/scientific-outputs` owns `graphical/`, `headless/snapshot.py`,
  `data_objects/`, `core/context.py`. It is adding matplotlib figures as an
  output type, heatmap colorbars, and a `interactive_pipe.draw` overlay
  module.
Their features are not in your base. Do not document them as existing; leave
a clearly marked placeholder heading in the skill for each ("Controls from
type hints", "Figures and overlays") with one line saying it is filled in at
merge time. You own `pyproject.toml`, `cli.py`, a new `__main__.py` and its
helpers, the skill, `readme.md`, `docs/index.md`, `docs/faq.md`,
`docs/guide/examples.md`, and the `.github/workflows/` files.
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

### 1. Rewrite the skill against the code as it is now

`.claude/skills/build-interactive-pipeline/SKILL.md` got additive patches
from two branches tonight. Rewrite it as one coherent document, verified
against the code — run every code block in it (extract them in a test, see
item 5). It must cover, briefly and correctly:

- the scaffold, and what the pipeline body accepts and rejects now
  (`PipelineSyntaxError`; literal kwargs, nested calls, `return f(x)`,
  indented scopes, dotted calls);
- the control table, including `flip=True`, colliding names
  (`amplify.gain`), and how to target one filter's parameter;
- outputs a filter can return and how they are displayed;
- `context` / `layout` / `events` / `audio`, with `layout.style` colormap;
- **the check-your-work loop without a display** — `describe()` →
  `snapshot()` → read the PNG → `sweep()` — as the default way for an agent
  to work, at pipeline level and at single-filter level;
- headless use, `save()`, tuning files, `INTERACTIVE_PIPE_GUI` /
  `INTERACTIVE_PIPE_SNAPSHOT`;
- an up-to-date table of error messages and fixes.

Keep it short enough to be read in full each time (aim for under 200 lines);
move depth into the docs and link it. Have the frontmatter `description`
say when to use it in terms an agent will match on (GUI from functions,
sliders, visual debugging, image / signal processing tuning, headless
snapshot).

### 2. Ship the skill and agent docs in the wheel

- The skill must be one source of truth: move it under
  `src/interactive_pipe/` as package data and keep
  `.claude/skills/build-interactive-pipeline/SKILL.md` working for this
  repository (a symlink does not survive wheels or Windows checkouts —
  prefer a test asserting the two files are identical, or generate one from
  the other; decide and document).
- `pyproject.toml` package-data so it lands in both the wheel and the sdist.
  Verify by building the wheel into a temporary directory
  (`$PY -m build` if available, otherwise `$PY -m pip wheel . --no-deps -w <tmp>`)
  and listing its contents. Do not install anything into the shared venv; a
  throwaway venv under the scratch directory is fine if you need one.
- `interactive_pipe.skill_path()` (or similar) returns the installed file.

### 3. Command line: `python -m interactive_pipe` and an `interactive-pipe` script

Standard library `argparse` only, no new dependency, fast to import (do not
import GUI toolkits or matplotlib for `--help`).

- `interactive-pipe skill` — print the skill to stdout;
  `interactive-pipe skill --install [--user | --project DIR]` — copy it to
  `~/.claude/skills/build-interactive-pipeline/` or `DIR/.claude/skills/...`,
  refusing to overwrite a different existing file without `--force`. Also
  offer `--agents-md` to print a short block suitable for pasting into an
  `AGENTS.md` / `CLAUDE.md` of a project that uses the library.
- `interactive-pipe doctor` — version, Python, which backends are importable
  (qt binding found, dpg, mpl, ipywidgets, gradio) with the pip extra to
  install for each missing one, whether a display is available, and which
  backend `gui="auto"` would pick. This answers most "nothing shows up"
  questions. Importing a backend must not open anything.
- `interactive-pipe snapshot SCRIPT.py [-o OUT.png] [-- script args]` — run
  an unmodified user script with `INTERACTIVE_PIPE_SNAPSHOT` set (the
  mechanism exists, see `cli.py` and `plan_agent_snapshot_loop.md` item 7)
  and print the written paths. Decide what happens when the script builds
  several pipelines or calls one several times, and make sure a script whose
  pipeline call sits under `if __name__ == "__main__":` works (`runpy` with
  `run_name="__main__"`).
- `interactive-pipe describe SCRIPT.py [--json]` — print the controls and
  outputs of the pipelines the script builds, without running a GUI. If this
  needs a hook that does not exist yet, add the smallest one.
- `interactive-pipe demo [NAME]` — list and run the bundled demos only if the
  demos can be shipped cheaply (they are outside the package today; the
  audio/image assets are large). Otherwise skip and say so.
- Register the console script in `pyproject.toml`. Tests call the CLI
  in-process (`main(argv)`) and once through `python -m interactive_pipe`.

### 4. Run every demo headless and fix what is stale

- A test (parametrised over `demo/*.py` and `samples/*.py`) that runs each
  script with `INTERACTIVE_PIPE_SNAPSHOT` pointing to a temp folder and
  asserts a non-blank PNG is produced — or that the script is in an explicit
  skip list with a reason (needs audio hardware, needs user input...). This
  is the regression net the library was missing for its examples.
- Look at each produced snapshot with the Read tool. Fix demos that are
  broken or misleading; note anything that looks like a library bug in
  Status rather than fixing library code owned by another branch.
- Regenerate nothing under `docs/images/` except what you add yourself.

### 5. Docs that agents and newcomers land on

- A test that extracts the python code blocks of `readme.md`, the skill and
  `docs/getting-started/quickstart.md` and executes those that are
  self-contained, headless (`INTERACTIVE_PIPE_GUI=headless` or the snapshot
  variable). Mark non-runnable fragments explicitly rather than skipping
  silently. Fix the blocks that fail.
- `readme.md`: after the quick taste, a short "Works without a display"
  section (three lines: `snapshot`, `sweep`, the CLI) and a "Using it with a
  coding agent" section pointing to `interactive-pipe skill --install`.
- `docs/index.md` and `docs/faq.md`: same pointers; add FAQ entries for the
  new error messages people will hit (`PipelineSyntaxError`, unknown
  parameter, renamed controls).
- The docs build has never been run tonight (`mkdocs` is not in the shared
  venv). Create a throwaway venv outside the repository (under
  `/tmp/claude-1000/` or `$TMPDIR`), install the `docs` extra there, run
  `mkdocs build --strict` against this worktree, and fix what it reports
  (broken links, missing nav entries, bad `:::` references). Check that
  `llms.txt` / `llms-full.txt` are generated and contain the new guide pages.
  If network access is unavailable, say so in Status and move on.
- `CHANGELOG.md` "Unreleased": your own bullets.

### 6. CI

Check `.github/workflows/pytest.yaml`: do the new tests (snapshots need
matplotlib only; GUI smoke tests need offscreen Qt) run there with the right
environment variables and extras? Adjust the workflow if a new test would
fail or be silently skipped in CI. Do not add a publishing step.

## Status

**Summary (03:10 CET):** all 6 items done, plus a review pass. Commits on
`feature/agent-packaging` after `c515a6a`: skill rewrite `df426b5`, skill in
the wheel `152d4de`, CLI `820bbfd`, demo test `c614709`, demo fixes `844f3e4`,
docs `ead18ad` `5c95beb`, windowless GUI stand-in `44001de`, CI `8d7a38e`,
review fixes `c042a95` `5a68af0` `9e29f4a`, and the commits of this file.
Final state: `950 passed, 6 skipped` (shared venv), `761 passed, 47 skipped` in
a CI-like Python 3.9 env with only the `[pytest]` dependencies and no display;
ruff format / check clean; pyright 8 errors, the same as the base (all in
`graphical/`); `mkdocs build --strict` clean. Nothing pushed, no PR, no other
branch or checkout touched, nothing installed in the shared venv (throwaway
venvs in the scratch folder only).

Agent run of 2026-11-14, started 02:02 CET, autonomous (nobody reachable
before 11:30). Environment check: the shared interpreter imports
`interactive_pipe` from this worktree's `src/`; baseline `867 passed, 6 skipped`
reproduced before any change.

### 1. Skill rewrite — done

- `SKILL.md` rewritten as one document (under 200 lines): scaffold, what the
  pipeline body accepts / rejects, control table (checkbox shorthand, name
  collisions, targeting one filter), outputs, proxies (with `layout.style`
  colormap), the describe → snapshot → read → sweep loop (pipeline and single
  filter), headless / `save` / tuning / environment variables / CLI, and an
  error table whose messages were copied from the code's actual output.
  Placeholder headings "Controls from type hints" and "Figures and overlays"
  say they are filled in at merge time.
- Frontmatter `description` rewritten around what an agent matches on (GUI from
  functions, sliders, image / signal / audio tuning, visual debugging,
  headless snapshot).
- Every python block runs: `test/doc_code_blocks.py` (helper, reused in item 5)
  extracts the blocks; an HTML comment above a block marks it
  `code: skip <reason>` (reason mandatory), `code: continue` (appended to the
  previous plain block) or `code: raises <Exception>`. Blocks run as scripts in
  a temp folder with `INTERACTIVE_PIPE_SNAPSHOT` set and `/tmp/` redirected.
  Tests: `test/test_skill_code_blocks.py`.
- Snapshots of the skill example looked at (out, sweep, single-filter sweep).
- **Library issue noticed (not fixed, `headless/snapshot.py` belongs to
  `feature/scientific-outputs`)**: the snapshot renderer ignores
  `layout.style(colormap=...)` — the skill's "Luma" heatmap is rendered gray in
  the PNG while every GUI backend shows it in viridis. An agent following the
  loop would think its colormap call is broken.

### 2. Skill in the wheel — done

- Source of truth: `src/interactive_pipe/agent/build-interactive-pipeline/SKILL.md`
  (package data, `pyproject.toml` glob `agent/*/SKILL.md`). The repository's
  `.claude/skills/build-interactive-pipeline/SKILL.md` stays as a byte-identical
  copy (no symlink: wheels and Windows checkouts), enforced by
  `test_repository_copy_is_identical_to_the_packaged_skill`, whose failure
  message gives the resync command
  (`python -m interactive_pipe skill --install --project . --force`, item 3).
  Merge note: the other branches' edits to the `.claude/` copy will merge into
  that copy and make this test fail until the packaged file gets them too —
  that is the intended signal.
- New subpackage `interactive_pipe.agent` (standard library only): `skill_path()`,
  `skill_text()`, `skill_install_dir()`, `install_skill()` (refuses to overwrite
  a different file without `force`) and the `AGENTS.md` block.
  `interactive_pipe.skill_path` is exported (additive hunk in `__init__.py`).
- Verified: `python -m build` (throwaway venv in the scratch folder, on a copy of
  the tree) puts the skill in both the wheel and the sdist; in a fresh venv with
  only the wheel installed, `interactive_pipe.skill_path()` points to an existing
  file in site-packages.
- Tests: `test/test_agent_skill_packaging.py`.

### 3. Command line — done

- `python -m interactive_pipe` (`__main__.py`) and the console script
  `interactive-pipe` (`[project.scripts]`) both call
  `interactive_pipe.agent.command_line:main(argv) -> int`; argparse only.
  Helpers: `agent/doctor.py`, `agent/run_script.py`.
- `skill` prints the skill; `--install` defaults to `--user`
  (`~/.claude/skills/...`), `--project DIR`; refuses a different existing file
  without `--force` (exit 1); `--agents-md` prints the AGENTS.md block;
  `--path` prints the packaged file's path (extra, cheap).
- `doctor [--json]`: version + path, Python, each backend (import of the module
  `gui=` would use; Qt binding name and version; the pip extra when missing),
  display (Linux: `DISPLAY` / `WAYLAND_DISPLAY`; notes for
  `QT_QPA_PLATFORM=offscreen` and `MPLBACKEND=Agg`), what `gui="auto"` picks
  (same order as `choose_backend.py`, `INTERACTIVE_PIPE_GUI` first) and advice
  (no display → snapshot / headless). Logging is muted during the imports (the Qt
  cascade logs every missing binding). Tested: no `QApplication` is created.
- `snapshot SCRIPT.py [-o OUT] [--max-calls N] [-- args]` and
  `describe SCRIPT.py [--json] [--max-calls N] [-- args]`: the script runs
  in-process with `runpy.run_path(run_name="__main__")` (so `if __name__ ==
  "__main__":` works), its folder on `sys.path`, `sys.argv` set to its
  arguments; `INTERACTIVE_PIPE_GUI` is removed for the run (a `headless` value
  would bypass the snapshots), matplotlib forced to Agg; everything is restored
  afterwards.
- Smallest hook added: `interactive_pipe.cli.set_snapshot_hook()` (a module-level
  callback, None by default) and 7 lines in `pipeline_decorator._snapshot_launcher`
  calling it with `(name, headless_pipeline, render)`. Without the hook the
  `INTERACTIVE_PIPE_SNAPSHOT` behaviour is unchanged.
- Decisions:
  - Several pipelines / several calls: **every call writes its own PNG**:
    `<folder>/<pipeline>.png`, then `<pipeline>_2.png`... for a repeated call;
    with `-o out.png`: `out.png`, `out_2.png`...; `{name}` patterns work as for
    the environment variable. Same folder / file rule as the variable (trailing
    `/` or existing folder = folder; `.png` added when no suffix).
  - Default output: `<tempdir>/interactive_pipe_snapshots/<script stem>/`, outside
    the user's repository; paths are printed.
  - `--max-calls` (default 10) stops the script (a `BaseException`, not
    swallowed by `except Exception`) so a script looping over a dataset ends.
  - Script failure: traceback on stderr, exit 1, snapshots written so far are
    still listed; the script's own `sys.exit(n)` is returned. No pipeline call:
    message + exit 1.
  - `describe` renders into a temporary folder (deleted), prints each pipeline
    once (first call); the script's own prints go to stderr so `--json` output
    is parseable.
  - Not captured: `gui=None` pipelines (the script already runs them headless)
    and pipelines that are defined but never called.
- `demo [NAME]`: **skipped**. The demos are outside the package and
  `demo/images` + `demo/audio` weigh several MB; shipping them would bloat the
  wheel for every user. `interactive-pipe snapshot demo/xxx.py` covers the
  repository case.
- `--help` imports no GUI toolkit (checked with `-X importtime` in a test).
  Deviation: it still imports matplotlib (and cv2 when installed), because
  `import interactive_pipe` does (`data_objects/curves.py` imports pyplot at
  module level, a file owned by `feature/scientific-outputs`); making that lazy
  is left for review.
- Verified with the built wheel in a fresh venv (no Qt there): the
  `interactive-pipe` script runs `doctor` and `snapshot table_demo.py`.
- `CLAUDE.md`: short additive section on the skill copy and the command.
- Tests: `test/test_command_line.py` (in-process `main(argv)`, and through
  `python -m interactive_pipe` in a subprocess).

### 4. Every demo headless — done (`c614709`, `844f3e4`)

- `test/test_demos_headless.py`, parametrised over the 17 `demo/*.py` and 3
  `samples/*.py`: each script runs unmodified as `__main__` through
  `run_script` (the code behind `interactive-pipe snapshot`) and every PNG it
  writes must be > 2 kB and not blank. In-process (~30 s for all) rather than
  one subprocess per script; the control registry (keyed by module + qualname,
  and every script is `__main__`) is isolated per script with `monkeypatch`, and
  `graphviz` is masked so `graph_representation(view=True)` cannot open a viewer.
- Explicit lists: `samples/object_oriented_pipeline_declarations.py` must run
  (exit 0) but has no GUI pipeline (HeadlessPipeline of `FilterCore`s). Not
  collected: `samples/interact_sample/` (`@interact` opens its window at import
  time and ignores `INTERACTIVE_PIPE_SNAPSHOT`) and `demo/multi_image.ipynb`.
- Every snapshot was looked at. Fixed:
  - `panel_position_demo.py`: the default crop (100×100 px at the origin, sized
    for its generated 300×200 fallback image) showed a blank white corner of the
    512×512 elephant. The crop is now in percent of the image; default = whole
    image. Checked with a sweep over `crop_x` / `crop_width`.
  - `grouped_controls_demo.py`, `detached_panel_demo.py`, `panel_demo.py`,
    `panel_position_demo.py`: blur and sharpen used a per-pixel Python loop,
    ~5 s per slider move on the demo image; replaced by a vectorized box blur
    (~40 ms), tested equal to the former loop.
- Looked fine / by design: the two `decorated_pipeline*` samples show
  solid-colour images (their input is a constant 1-pixel colour);
  `grouped_controls` / `panel_demo` titles mention a text overlay the demo does
  not draw (the code says so: "not actually drawing text").
- Library issues noticed, not fixed (files owned by other branches):
  - snapshot renderer ignores `layout.style(colormap=...)` (see item 1);
  - running several scripts in one process shares the control registry between
    their same-named `__main__` filters (`process_image: hue_shift not in ...`).
    Irrelevant for one script per process (the CLI), but anything running
    several user scripts in one interpreter (notebooks re-running cells from
    different files?) would hit it.

### 5. Docs — done (`ead18ad`, `5c95beb`)

- `test/test_doc_code_blocks.py` runs every python block of `readme.md` and
  `docs/getting-started/quickstart.md` (the skill's in its own test), headless.
  New marker `<!-- code: file image_filters.py -->` for the quickstart's
  two-file "keep your library clean" example (the block is written as a module
  next to the later blocks). Fix needed in the quickstart: `app.py` now names
  its `input_image`, which the following headless / `save` blocks (marked
  `continue`) use. No block needed a `skip`. The helper itself is unit-tested
  (markers, invalid markers, `raises`). `docs/guide/snapshots.md` is not in the
  list: its block reads `demo/images/` and regenerates the page's own
  `docs/images/` pictures.
- `readme.md`: "Works without a display" (snapshot, sweep, CLI) and "Using it
  with a coding agent" sections; a link to the new guide page in "Learn more".
- `docs/index.md`: "Without a display, and with coding agents" section.
- `docs/faq.md`: the in-place answer was **stale** ("there are no checks") — inputs
  are read-only by default since the read-only-inputs work; rewritten with the
  real error and `inplace=True` / `readonly_inputs=False`. New entries:
  `PipelineSyntaxError`, unknown keyword arguments, `amplify.gain` renamed
  controls, "nothing shows up" (doctor), coding agents.
- New page `docs/guide/command-line.md` (nav: Guide → "Command line & agents"),
  with real `doctor` / `snapshot` / `describe` outputs (the doctor one from the
  Qt-less throwaway venv without a display). `docs/guide/examples.md`: demos run
  headless.
- **mkdocs**: throwaway venv in the scratch folder (network available) with the
  `docs` extra; `mkdocs build --strict` against this worktree passes with no
  warning (also before my pages were added). `llms.txt` lists the snapshots and
  command-line pages; `llms-full.txt` contains them, the FAQ entries and the
  changelog; the HTML-comment markers do not appear in either.
- `CHANGELOG.md` "Unreleased": new "Command line and coding agents" subsection,
  two bullets at the end of "Improvements & bug fixes" (demos, FAQ).

### 6. CI — done (`44001de` + workflow commit)

- Reproduced the CI environment locally: throwaway Python 3.9 venv with only
  the `[pytest]` extra's dependencies (no Qt, dpg, ipywidgets, gradio, pandas),
  no `DISPLAY`, no `MPLBACKEND` / `QT_QPA_PLATFORM`. **The base branch already
  failed 4 tests there** (CI would be red): `test_headless_save` (expected a
  `.csv` table, which needs pandas) and 3 in `test_snapshot_env` (expected a GUI
  object under `INTERACTIVE_PIPE_SNAPSHOT`, which needs Qt / ipywidgets). My new
  demo test added a 5th: `key_event_demo.py` calls
  `demo.pipeline.bind_key_to_context(...)`, and without Qt `.pipeline` was the
  bare `HeadlessPipeline`.
- Fix (`helper/pipeline_decorator.py`, not owned by the other branches): when
  the requested backend cannot be built under `INTERACTIVE_PIPE_SNAPSHOT`, a
  windowless `InteractivePipeGUI` subclass stands in (`init_app` no-op, `run`
  raises), so scripts configuring `.pipeline` and the 2D results behave the
  same with or without the backend; `HeadlessPipeline` only if even that fails
  (the existing fallback test now covers that path). The pandas test expects
  `.pkl` without pandas. Result in the CI-like env: `753 passed, 47 skipped`.
- `.github/workflows/pytest.yaml`:
  - `MPLBACKEND=Agg` and `QT_QPA_PLATFORM=offscreen` for every job;
  - the existing matrix job also runs `interactive-pipe --version / doctor /
    skill --path` (console script of the editable install);
  - new job `gui-backends` (Python 3.12, `.[full]`, apt `libegl1 libxkbcommon0
    libfontconfig1` for Qt's offscreen platform, `pytest -rs`) so the 47 backend
    smoke tests skipped in the matrix job run somewhere. Locally the full suite
    with every backend and no display passes. **Not verified on GitHub** (no
    push allowed): the apt package list is the usual one for offscreen Qt on
    ubuntu-24.04 but may need adjusting on the first run.
- No publishing step added. The docs workflow already runs
  `mkdocs build --strict` with the `docs` extra (verified locally, item 5).

### Review pass — done (`c042a95`, `5a68af0`, `9e29f4a`)

An independent read-only review of the whole diff (separate agent, every
finding reproduced by running code) found 9 defects, all fixed with tests:
1. relative `-o` resolved after the script's own `os.chdir` → made absolute first;
2. `@interact` scripts made `interactive-pipe snapshot` hang (invisible Qt event
   loop): during a run, `filter_decorator.get_interactive_pipeline_class` is
   swapped (at runtime, no edit of that file, which `feature/declare-less` owns)
   for a GUI class whose `run` goes through the snapshot hook; restored after.
   `samples/interact_sample/` is now in the demo test;
3. `my_filter.interact()` bypassed the hook → it now uses it when installed
   (`helper/filter_entry_points.py`, not owned by the other branches);
4. the demo test's "not blank" check could not fail (the PNG's titles and
   caption are never uniform) → checks the returned outputs instead
   (`PipelineCall.results`), with a `UNIFORM_BY_DESIGN` list of 3 scripts;
5. SIGINT / SIGTERM handlers (reset by the Qt backend) restored after a run;
6. modules imported from the script's folder are dropped from `sys.modules`;
7. `{name}/` followed a different rule than the environment variable;
8. skill claimed the bare environment variable writes one PNG per call (it
   overwrites `<pipeline>.png`) → corrected;
9. skill error table quoted the `Control(...)` message for an out-of-range
   default; the tuple form says something else (below) → corrected.

### Left for review

- **Library issues seen, not fixed (owned by the other branches):**
  - snapshot renderer ignores `layout.style(colormap=...)` (heatmaps rendered
    gray in PNGs) — `headless/snapshot.py`;
  - `@interactive(gain=(5, [0, 3]))` (default outside the range) raises
    `Cannot create a control from gain=(5, [0, 3]): min=5 max=[0, 3] - max
    parameter should be numerical too`: the abbreviation parser reads the
    default as a min — `helper/control_abbreviation.py`;
  - the control registry is keyed by `module.qualname`, so two `__main__`
    scripts run in one process share same-named filters' controls (the tests
    isolate it; the CLI runs one script per process);
  - `import interactive_pipe` imports `matplotlib.pyplot` (and cv2), so
    `interactive-pipe --help` takes ~1-3 s — `data_objects/curves.py`.
- Merge notes: the `.claude/skills/` copy must equal the packaged skill (test);
  the placeholder headings "Controls from type hints" / "Figures and overlays"
  in the skill are to be filled by the other branches; `run_script` swaps
  `filter_decorator.get_interactive_pipeline_class` by name (if that import is
  renamed, `@interact` scripts are no longer intercepted —
  `test_interact_decorator_renders_instead_of_opening_a_window` would fail).
- The new `gui-backends` CI job was not run on GitHub (apt package list may
  need adjusting on the first run).
- `docs/guide/snapshots.md`'s code block is not in the doc-block test (it
  regenerates `docs/images/`).
