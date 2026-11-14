# Command line & coding agents

`pip install interactive-pipe` also installs an `interactive-pipe` command
(`python -m interactive_pipe` is the same). It needs no GUI toolkit and never
opens a window.

```bash
interactive-pipe skill [--install [--user | --project DIR] [--force]] [--agents-md] [--path]
interactive-pipe doctor [--json]
interactive-pipe snapshot SCRIPT.py [-o OUT] [--max-calls N] [-- script arguments]
interactive-pipe describe SCRIPT.py [--json] [--max-calls N] [-- script arguments]
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
interactive_pipe 0.9.4 (.../site-packages/interactive_pipe)
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
- A failing script prints its traceback and exits with code 1; the snapshots
  written before the failure are listed.
- Pipelines decorated with `gui=None` (headless) are not captured: the script
  already runs them without a window.

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
