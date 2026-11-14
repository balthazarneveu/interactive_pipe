# Command line & agent skill

The `interactive-pipe` command (also `python -m interactive_pipe`) is
documented with examples in [Command line & coding agents](../guide/command-line.md):

| Command | What it does |
|---|---|
| `interactive-pipe skill [--install [--user \| --project DIR] [--force]] [--agents-md] [--path]` | print or install the agent skill |
| `interactive-pipe doctor [--json]` | installed backends, display, what `gui="auto"` picks |
| `interactive-pipe snapshot SCRIPT.py [-o OUT] [--set NAME=VALUE] [--output NAME] [-- args]` | run an unmodified GUI script, one PNG per pipeline call |
| `interactive-pipe sweep SCRIPT.py --param NAME=V1,V2 [--steps NAME=N] [--set ...] [-o OUT]` | a contact sheet over parameter values, per pipeline call |
| `interactive-pipe describe SCRIPT.py [--json] [--max-calls N] [-- args]` | the controls and outputs of the pipelines a script runs |
| `interactive-pipe check SCRIPT.py [--json] [--set ...] [-- args]` | build and run every pipeline once, report outputs, warnings and errors |
| `interactive-pipe --version` | the installed version |

The environment variable `INTERACTIVE_PIPE_SNAPSHOT=<path.png or folder/>`
makes GUI-decorated pipelines render a snapshot instead of opening a window
([Snapshots](../guide/snapshots.md#without-editing-the-script-interactive_pipe_snapshot)).

::: interactive_pipe.skill_path

::: interactive_pipe.agent.command_line.main
