"""The ``interactive-pipe`` command (also ``python -m interactive_pipe``).

Subcommands::

    interactive-pipe skill [--install [--user | --project DIR] [--force]] [--agents-md]
    interactive-pipe doctor [--json]
    interactive-pipe snapshot SCRIPT.py [-o OUT] [--set NAME=VALUE] [--output NAME] [--pipeline NAME] [-- script args]
    interactive-pipe sweep SCRIPT.py --param NAME=V1,V2 [--steps NAME=N] [--set ...] [--output NAME] [-o OUT]
    interactive-pipe describe SCRIPT.py [--json] [--max-calls N] [-- script args]
    interactive-pipe check SCRIPT.py [--json] [--set NAME=VALUE] [-- script args]

Standard library only at import time: GUI toolkits are imported by ``doctor``
(to check them) and by the user script, never for ``--help``.
"""

import argparse
import json
import sys
from typing import List, Optional, Sequence, Tuple

PROG = "interactive-pipe"
SCRIPT_COMMANDS = ("snapshot", "sweep", "describe", "check")


def _split_script_args(argv: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Split at the first ``--``: (our arguments, the script's arguments)."""
    argv = list(argv)
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


PARAMETER_HELP = """parameter names: a parameter (gain), a control name or filter.parameter.
values are converted to the control's type: numbers, true/false for checkboxes,
the choice for dropdowns, comma-separated numbers for ranges, points and regions
(--set seed=0.2,0.4). Swept values are comma-separated (--param gain=0.5,1,2), or
';'-separated for ranges, points and regions (--param seed="0.1,0.1;0.6,0.4")."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="interactive_pipe helpers for coding agents and headless use.",
        epilog="Docs: https://balthazarneveu.github.io/interactive_pipe/",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    skill = commands.add_parser(
        "skill",
        help="print or install the agent skill (instructions for coding agents)",
        description="Print the agent skill (SKILL.md) to stdout, or install it for Claude Code.",
    )
    skill.add_argument("--install", action="store_true", help="copy SKILL.md where Claude Code finds skills")
    where = skill.add_mutually_exclusive_group()
    where.add_argument(
        "--user", action="store_true", help="install in ~/.claude/skills/ (default with --install unless --project)"
    )
    where.add_argument("--project", metavar="DIR", help="install in DIR/.claude/skills/")
    skill.add_argument("--force", action="store_true", help="overwrite a different existing SKILL.md")
    skill.add_argument(
        "--agents-md", action="store_true", help="print a short block to paste into a project's AGENTS.md / CLAUDE.md"
    )
    skill.add_argument("--path", action="store_true", help="print the path of the packaged SKILL.md")

    doctor = commands.add_parser(
        "doctor",
        help="installed backends, display, what gui='auto' picks",
        description="Check which GUI backends are installed, whether a display is available and which backend "
        "gui='auto' picks. No window is opened.",
    )
    doctor.add_argument("--json", action="store_true", help="machine-readable output")

    script_commands = {
        "snapshot": "run a script and write a PNG for each pipeline call instead of opening a window",
        "sweep": "run a script and write a contact sheet over parameter values for each pipeline call",
        "describe": "run a script headless and print the controls and outputs of its pipelines",
        "check": "build and run every pipeline of a script once, without a window, and report problems",
    }
    for name, help_text in script_commands.items():
        command = commands.add_parser(
            name,
            help=help_text,
            description=help_text[0].upper() + help_text[1:] + ". The script is run unmodified, as __main__ "
            "(pass its own arguments after --). Pipelines decorated with a GUI are captured; gui=None pipelines "
            "are not" + (" (check runs those taking no input)." if name == "check" else "."),
            epilog=PARAMETER_HELP if name != "describe" else None,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        command.add_argument("script", help="python script calling an @interactive_pipeline function")
        if name in ("snapshot", "sweep"):
            command.add_argument(
                "-o",
                "--out",
                dest="out",
                metavar="PATH",
                help="PNG file, folder (trailing /) or pattern with {name}; default: "
                "<tmp>/interactive_pipe_snapshots-<user>/<script>/",
            )
        if name in ("describe", "check"):
            command.add_argument("--json", action="store_true", help="machine-readable output")
        if name != "describe":
            command.add_argument(
                "--set",
                action="append",
                metavar="NAME=VALUE",
                help="parameter value for the run (repeatable), e.g. --set gain=2 --set mode=dark --set seed=0.2,0.4",
            )
        if name == "sweep":
            command.add_argument(
                "--param",
                action="append",
                metavar="NAME=V1,V2",
                help="values to sweep (one or two parameters), e.g. --param gain=0.5,1,2",
            )
            command.add_argument(
                "--steps",
                action="append",
                metavar="NAME=N",
                help="sweep N values over the control's declared range, e.g. --steps gain=5",
            )
        if name in ("snapshot", "sweep"):
            command.add_argument(
                "--output",
                metavar="NAME",
                help="output(s) to show: a name, an index or a comma-separated list"
                + ("; 'all' shows every output in each cell" if name == "sweep" else ""),
            )
        command.add_argument("--pipeline", metavar="NAME", help="only this pipeline (when the script calls several)")
        command.add_argument(
            "--max-calls",
            type=int,
            default=10,
            metavar="N",
            help="stop the script after N pipeline calls (default: 10)",
        )
    return parser


def _cmd_skill(args: argparse.Namespace) -> int:
    from interactive_pipe.agent import AGENTS_MD_BLOCK, install_skill, skill_path, skill_text

    if args.path:
        print(skill_path())
        return 0
    if args.agents_md:
        print(AGENTS_MD_BLOCK, end="")
        return 0
    if not args.install:
        if args.user or args.project or args.force:
            print(f"{PROG} skill: --user / --project / --force need --install", file=sys.stderr)
            return 2
        print(skill_text(), end="")
        return 0
    try:
        target = install_skill(user=args.project is None, project=args.project, force=args.force)
    except FileExistsError as exc:
        print(f"{PROG} skill: {exc}", file=sys.stderr)
        return 1
    print(f"skill installed: {target}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from interactive_pipe.agent.doctor import diagnose, format_report

    report = diagnose()
    print(json.dumps(report, indent=2) if args.json else format_report(report))
    return 0


def _report(run, command: str, script: str) -> int:
    """What went wrong, on stderr, each error once; returns the exit code."""
    out = sys.stderr
    if run.usage_error:
        print(f"{PROG} {command}: {run.usage_error}", file=out)
        return 2
    if run.error:
        print(f"\n{PROG}: the script failed:\n{run.error}", file=out)
    if run.stopped_early:
        print(f"{PROG}: stopped the script after {len(run.calls)} pipeline calls (--max-calls)", file=out)
    failed = run.failed_calls
    if failed:
        # the error was printed above (by the script's failure) or by the script itself
        for call in failed:
            raised_here = run.exception is call.error
            print(
                f"{PROG} {command}: pipeline {call.name!r} raised {type(call.error).__name__}"
                + (", see above" if raised_here else f" (caught by the script): {call.error}"),
                file=out,
            )
        return run.exit_code or 1
    if not run.calls:
        if run.skipped:
            print(
                f"{PROG} {command}: the script called {', '.join(sorted(set(run.skipped)))}, not --pipeline", file=out
            )
            return 2
        print(
            f"{PROG} {command}: no GUI-decorated pipeline was called by {script} "
            "(gui=None pipelines and pipelines that are only defined are not captured)",
            file=out,
        )
        return run.exit_code or 1
    return run.exit_code


def _cmd_run(args: argparse.Namespace, script_args: List[str]) -> int:
    from interactive_pipe.agent.parameters import (
        ParameterError,
        parse_assignments,
        parse_steps,
        parse_sweep_assignments,
    )
    from interactive_pipe.agent.run_script import CallOptions, run_script

    command = args.command
    try:
        options = CallOptions(
            mode=command,
            settings=parse_assignments(getattr(args, "set", None), "--set"),
            axes=parse_sweep_assignments(getattr(args, "param", None)),
            steps=parse_steps(getattr(args, "steps", None)),
            output=getattr(args, "output", None),
            pipeline=args.pipeline,
        )
    except ParameterError as exc:
        print(f"{PROG} {command}: {exc}", file=sys.stderr)
        return 2
    if command == "sweep" and not options.axes and not options.steps:
        print(f"{PROG} sweep: nothing to sweep: add --param NAME=V1,V2,... or --steps NAME=N", file=sys.stderr)
        return 2
    try:
        run = run_script(
            args.script, script_args, output=getattr(args, "out", None), max_calls=args.max_calls, options=options
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"{PROG} {command}: {exc}", file=sys.stderr)
        return 2
    if command == "check":
        from interactive_pipe.agent.check import check_report, format_check

        report = check_report(run)
        print(json.dumps(report, indent=2) if args.json else format_check(report))
        return report["exit_code"]
    if command == "describe":
        seen = set()
        unique = [call for call in run.calls if not (call.name in seen or seen.add(call.name))]
        if args.json:
            print(json.dumps([call.description for call in unique], indent=2))
        else:
            for call in unique:
                print(call.summary)
                print()
    elif run.written:
        kind = "sweep(s)" if command == "sweep" else "snapshot(s)"
        print(f"\n{len(run.written)} {kind} written:")
        for call in run.calls:
            if not call.failed:
                print(f"  {call.path}  (pipeline {call.name!r})")
    return _report(run, command, args.script)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point of the ``interactive-pipe`` command; returns the exit code."""
    own_args, script_args = _split_script_args(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(own_args)
    if args.version:
        from interactive_pipe import __version__

        print(f"interactive_pipe {__version__}")
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    if script_args and args.command not in SCRIPT_COMMANDS:
        parser.error(f"arguments after -- are only used by the script commands: {script_args}")
    if args.command == "skill":
        return _cmd_skill(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    return _cmd_run(args, script_args)


if __name__ == "__main__":
    sys.exit(main())
