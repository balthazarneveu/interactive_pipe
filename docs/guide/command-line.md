# Command line & coding agents

`pip install interactive-pipe` also installs an `interactive-pipe` command
(`python -m interactive_pipe` is the same). It needs no GUI toolkit and never
opens a window.

```bash
interactive-pipe skill [--install [--user | --project DIR] [--force]] [--agents-md] [--path]
interactive-pipe doctor [--json]
interactive-pipe snapshot SCRIPT.py [-o OUT] [--set NAME=VALUE ...] [--output NAME] [--pipeline NAME] [--max-calls N] [-- script arguments]
interactive-pipe sweep SCRIPT.py --param NAME=V1,V2,... [--param ...] [--steps NAME=N] [--set ...] [--output NAME] [-o OUT] [-- script arguments]
interactive-pipe describe SCRIPT.py [--json] [--max-calls N] [-- script arguments]
interactive-pipe check SCRIPT.py [--json] [--set NAME=VALUE ...] [-- script arguments]
```

## `skill`: instructions for a coding agent

The package ships an agent skill: a short document teaching the decorators,
what a pipeline body may contain, the controls, the common error messages and,
above all, how to check visual work without seeing the window (describe →
snapshot → read the PNG → sweep).

```bash
interactive-pipe skill --install                # Claude Code, for all your projects: ~/.claude/skills/build-interactive-pipeline/
interactive-pipe skill --install --project .    # for one repository: ./.claude/skills/build-interactive-pipeline/
interactive-pipe skill                          # print it, for any other agent
interactive-pipe skill --agents-md >> AGENTS.md # a short block for AGENTS.md / CLAUDE.md
```

`--install` does not overwrite a `SKILL.md` that differs from the packaged one
(it may hold your edits) unless `--force` is given; run it again after upgrading
the package. From Python, `interactive_pipe.skill_path()` returns the installed
file.

## `doctor`: why does no window show up?

```text
$ interactive-pipe doctor
interactive_pipe 0.10.0 (.../site-packages/interactive_pipe)
Python 3.12.3 (/usr/bin/python3)
Platform Linux-6.8.0-x86_64-with-glibc2.39

Backends (gui=...):
  qt      missing needs PyQt6, PyQt5 or PySide6: No PyQt  -> pip install "interactive-pipe[qt6]"
  dpg     missing needs dearpygui: No module named 'dearpygui'  -> pip install "interactive-pipe[dpg]"
  mpl     ok      matplotlib 3.9.2
  nb      missing needs ipywidgets, in Jupyter: No module named 'ipywidgets'  -> pip install "interactive-pipe[notebook]"
  gradio  missing needs gradio: No module named 'gradio'  -> pip install "interactive-pipe[gradio]"

Display: NOT available (no DISPLAY / WAYLAND_DISPLAY)
gui="auto" picks: mpl (first importable of qt, dpg, mpl)

* gui="auto" picks mpl but no display was found: render PNGs instead (pipe.snapshot(...), `interactive-pipe snapshot script.py`) or use gui=None (headless)
* for the richest GUI: pip install "interactive-pipe[qt6]"
```

`--json` prints the same report as JSON. The backend choice follows the same
order as `gui="auto"`: `INTERACTIVE_PIPE_GUI` first, Jupyter, then Qt, Dear
PyGui and matplotlib.

## `check`: run after every edit

```text
$ interactive-pipe check demo/matplotlib_figure_demo.py
check demo/matplotlib_figure_demo.py: OK - 1 pipeline, 0 errors, 0 warnings
pipeline 'field_pipeline' (inputs: none)
  controls: separation = 1 slider(float) in [0.2, 2]
            charge_ratio = -1 slider(float) in [-2, 2]
  outputs : field      matplotlib.Figure
            potential  (160, 160) float64 [-5, 5]
```

Builds every pipeline of the script and runs it once without a window — the
pipelines the script calls with the values of that call, the pipelines it only
defines with their defaults when they take no input — then reports, in one
short screen that does not change from run to run:

- the pipelines, their inputs and controls;
- every output with its type, shape, dtype and value range;
- every warning: outputs that would be displayed misleadingly (clipped
  integers, values out of `[0, 1]`...), clamped values, anything the library or
  the script logs;
- errors with the file and line of your code: a `PipelineSyntaxError` in the
  pipeline function, a filter that raises, an output that cannot be displayed.

```text
check script.py: FAILED - 1 pipeline, 1 error, 0 warnings
pipeline 'process' (inputs: img)
  controls: gain = 1 slider(float) in [0, 2]
  outputs : not run (error)
error: script.py:8: pipeline 'process': filter 'amplify' raised NameError: name 'undefined_name' is not defined
```

Exit code 1 on an error, 2 for a wrong `--set`, else 0 (warnings do not fail).
`--json` prints the same report as a dictionary (`ok`, `exit_code`,
`pipelines`, `errors` with `file` / `line`, `warnings`). The script's own
prints go to stderr. A pipeline the script defines but does not call, and
that needs inputs, is listed as `not run`.

## `snapshot`: look at a GUI script without a display

Runs an unmodified script — as `__main__`, so a pipeline launched under
`if __name__ == "__main__":` is reached — and writes what each window would
show to a PNG instead of opening it ([Snapshots](snapshots.md) shows what is
rendered):

```text
$ interactive-pipe snapshot demo/key_event_demo.py -o shots/
interactive_pipe: snapshot of 'key_event_pipeline' written to shots/key_event_pipeline.png

1 snapshot(s) written:
  shots/key_event_pipeline.png  (pipeline 'key_event_pipeline')
```

- Every call of a GUI-decorated pipeline writes its own file:
  `shots/<pipeline>.png`, then `shots/<pipeline>_2.png` when the same pipeline is
  called again. With `-o out.png`: `out.png`, `out_2.png`, ...; `{name}` in the
  value is replaced by the pipeline name (`-o shots/{name}_v1.png`).
- Without `-o`, the files go to `<temp dir>/interactive_pipe_snapshots/<script>/`
  (outside your repository); the paths are printed.
- The script is stopped after `--max-calls` pipeline calls (default 10), so a
  script looping over a dataset ends.
- Arguments after `--` are the script's own (`sys.argv[1:]`):
  `interactive-pipe snapshot demo/color_demo.py -- --color blue`.
- A failing script prints its error once (without interactive_pipe's own
  frames) and exits with code 1; the snapshots written before the failure are
  listed. When a filter raised, the last line names the pipeline:
  `interactive-pipe snapshot: pipeline 'p' raised FilterError, see above`.
- `--output NAME` renders only that output (a name, an index, or a
  comma-separated list), like `snapshot(output=...)`; `--pipeline NAME` keeps
  one pipeline when the script calls several.
- Single-filter GUIs are captured too: `my_filter.interact(img)` and `@interact`
  write `<filter>.png`.
- Pipelines decorated with `gui=None` (headless) are not captured: the script
  already runs them without a window.
- A relative `-o` is relative to the folder you run the command from, even if
  the script changes directory.

### Set parameters: `--set`

```bash
interactive-pipe snapshot demo/time_wave_demo.py --set time=4
interactive-pipe snapshot script.py --set gain=2.0 --set mode=dark --set seed=0.2,0.4
```

`--set NAME=VALUE` (repeatable) sets a parameter for the snapshot, as
`pipe.snapshot(path, gain=2.0)` does. It wins over the values the script passes
to the pipeline call; the script's other values are kept.

- Names are those `snapshot()` accepts: a parameter name (`gain`), a control
  name, or `filter.parameter` for one filter only. An unknown name fails (exit
  code 2) with the available names and the closest match:
  `--set (pipeline 'pipe') got unexpected parameter name(s) 'gian'. Available
  parameters: gain, mode, seed. Did you mean 'gian' -> 'gain'?`
- Values are converted to the type of the control: numbers (an `int` slider
  refuses `2.5`), `true` / `false` (also `1/0`, `yes/no`, `on/off`) for a
  checkbox, the choice for a dropdown (`'shiny' is not one of the choices
  ['dark', 'light']`), comma-separated numbers for a range, a point or a region
  (`seed=0.2,0.4`). A parameter without control takes the type of its default.
- A value outside a slider's range is clamped, with a warning, like in the GUI.
- With several pipelines, a name only another pipeline has is applied to that
  one only.

## `sweep`: compare values of an unmodified script

```bash
interactive-pipe sweep script.py --param gain=0.5,1,2 -o sweep.png
interactive-pipe sweep script.py --param gain=0.5,1,2 --param mode=dark,light --output out -o grid.png
interactive-pipe sweep script.py --param seed="0.1,0.1;0.6,0.4" --set t=2
interactive-pipe sweep script.py --steps gain=5 --output all
```

The command-line form of `pipe.sweep(...)` ([Snapshots](snapshots.md)): one
contact sheet per pipeline call, with the script's inputs and values.

- `--param NAME=V1,V2,...` gives the values of one swept parameter (one or two
  parameters: a row or a grid). Values of a range, a point or a region are
  separated by `;` (quote them for the shell); `--param` repeated with the same
  name adds values.
- `--steps NAME=N` sweeps N values over the control's declared range (every
  choice of a dropdown, both states of a checkbox).
- `--output` chooses what each cell shows: an output name or index, a list, or
  `all` for the whole layout. Default: the only output, else the first image
  the swept parameters change, else the last image.
- `--set` fixes other parameters; `-o` is a file, a folder or a `{name}`
  pattern as for `snapshot` (default file name: `<pipeline>_sweep.png`).

This is the command-line form of the `INTERACTIVE_PIPE_SNAPSHOT` environment
variable, which still works on its own:
`INTERACTIVE_PIPE_SNAPSHOT=shots/ python demo/key_event_demo.py`.

## `describe`: list the controls of a script

```text
$ interactive-pipe describe demo/key_event_demo.py
Pipeline 'key_event_pipeline'
  inputs : img
  outputs: [out]
Filters (execution order):
  brighten(img) -> bright   [brightness=1]
  noise_burst(bright) -> out
Controls:
  brightness slider(float) = 1 in [0, 2] step 0.02  -> brighten.brightness
```

Same output as `pipeline.summary()`, once per pipeline the script calls;
`--json` prints the `pipeline.describe()` dictionaries. The script's own prints
go to stderr, so `--json` output can be piped to another tool.
