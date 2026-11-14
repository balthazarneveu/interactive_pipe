"""The ``interactive-pipe`` command (also ``python -m interactive_pipe``).

Subcommands::

    interactive-pipe skill [--install [--user | --project DIR] [--force]] [--agents-md]
    interactive-pipe doctor [--json]
    interactive-pipe snapshot SCRIPT.py [-o OUT] [--max-calls N] [-- script args]
    interactive-pipe describe SCRIPT.py [--json] [--max-calls N] [-- script args]

Standard library only at import time: GUI toolkits are imported by ``doctor``
(to check them) and by the user script, never for ``--help``.
"""

import argparse
import json
import sys
from typing import List, Optional, Sequence, Tuple

PROG = "interactive-pipe"


def _split_script_args(argv: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Split at the first ``--``: (our arguments, the script's arguments)."""
    argv = list(argv)
    if "--" in argv:
        index = argv.index("--")
        return argv[:index], argv[index + 1 :]
    return argv, []


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

    for name, help_text in (
        ("snapshot", "run a script and write a PNG for each pipeline call instead of opening a window"),
        ("describe", "run a script headless and print the controls and outputs of its pipelines"),
    ):
        command = commands.add_parser(
            name,
            help=help_text,
            description=help_text[0].upper() + help_text[1:] + ". The script is run unmodified, as __main__ "
            "(pass its own arguments after --). Pipelines decorated with a GUI are captured; gui=None pipelines "
            "are not.",
        )
        command.add_argument("script", help="python script calling an @interactive_pipeline function")
        if name == "snapshot":
            command.add_argument(
                "-o",
                "--output",
                help="PNG file, folder (trailing /) or pattern with {name}; default: "
                "<tmp>/interactive_pipe_snapshots/<script>/",
            )
        else:
            command.add_argument("--json", action="store_true", help="print describe() dicts as JSON")
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


def _report_failure(run, out) -> None:
    if run.error:
        print(f"\n{PROG}: the script failed:\n{run.error}", file=out)
    if run.stopped_early:
        print(f"{PROG}: stopped the script after {len(run.calls)} pipeline calls (--max-calls)", file=out)


def _cmd_run(args: argparse.Namespace, script_args: List[str]) -> int:
    from interactive_pipe.agent.run_script import run_script

    describe = args.command == "describe"
    try:
        run = run_script(
            args.script,
            script_args,
            output=None if describe else args.output,
            describe=describe,
            max_calls=args.max_calls,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"{PROG} {args.command}: {exc}", file=sys.stderr)
        return 2
    if describe:
        seen = set()
        unique = [call for call in run.calls if not (call.name in seen or seen.add(call.name))]
        if args.json:
            print(json.dumps([call.description for call in unique], indent=2))
        else:
            for call in unique:
                print(call.summary)
                print()
    else:
        print(f"\n{len(run.written)} snapshot(s) written:")
        for call in run.calls:
            print(f"  {call.path}  (pipeline {call.name!r})")
    _report_failure(run, sys.stderr)
    if not run.calls:
        print(
            f"{PROG} {args.command}: no GUI-decorated pipeline was called by {args.script} "
            "(gui=None pipelines and pipelines that are only defined are not captured)",
            file=sys.stderr,
        )
        return run.exit_code or 1
    return run.exit_code


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
    if script_args and args.command not in ("snapshot", "describe"):
        parser.error(f"arguments after -- are only used by snapshot and describe: {script_args}")
    if args.command == "skill":
        return _cmd_skill(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    return _cmd_run(args, script_args)


if __name__ == "__main__":
    sys.exit(main())
