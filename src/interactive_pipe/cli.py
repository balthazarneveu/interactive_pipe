"""Command-line and environment helpers to choose the GUI backend and window size.

Lets a script pick its backend / window size without editing code::

    from interactive_pipe import interactive_pipeline
    from interactive_pipe.cli import parse_gui_args

    args, gui_kwargs = parse_gui_args()
    demo = interactive_pipeline(**gui_kwargs)(my_pipeline)  # gui="auto" unless --gui given
    demo(img)

Environment variables (read when ``interactive_pipeline`` decorates a function):

- ``INTERACTIVE_PIPE_GUI``: one of auto/qt/dpg/mpl/nb/gradio/headless/none,
  used when the decorator was called with ``gui="auto"`` (the default).
- ``INTERACTIVE_PIPE_SIZE``: "fullscreen", "maximized" or "WxH" (e.g. "1280x800"),
  used when the decorator was not given a ``size``.

Precedence: CLI helper values > explicit decorator arguments (other than "auto") > environment.

This module only depends on the standard library and has no side effects on import.
"""

import argparse
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

GUI_ENV_VAR = "INTERACTIVE_PIPE_GUI"
SIZE_ENV_VAR = "INTERACTIVE_PIPE_SIZE"

GUI_CHOICES: Tuple[str, ...] = ("auto", "qt", "dpg", "mpl", "nb", "gradio", "headless")
# Accepted by the environment variable on top of GUI_CHOICES (aliases of "headless")
_HEADLESS_ALIASES = ("headless", "none")

SizeType = Union[str, Tuple[int, int]]


def parse_size(value: str) -> SizeType:
    """Parse a window size string.

    Returns "fullscreen" for "fullscreen"/"full", "maximized" for "maximized"/"max",
    or a ``(width, height)`` tuple for "WxH" (e.g. "1280x800").

    Raises:
        ValueError: If the value is not a recognized size.
    """
    if not isinstance(value, str):
        raise TypeError(f"size should be a string, got {type(value).__name__}")
    normalized = value.strip().lower()
    if normalized in ("fullscreen", "full"):
        return "fullscreen"
    if normalized in ("maximized", "max"):
        return "maximized"
    parts = normalized.split("x")
    if len(parts) == 2 and all(part.strip().isdigit() for part in parts):
        width, height = (int(part) for part in parts)
        if width > 0 and height > 0:
            return (width, height)
    raise ValueError(f"invalid size {value!r}: expected 'fullscreen', 'maximized' or 'WxH' (e.g. 1280x800)")


def _argparse_size(value: str) -> Tuple[int, int]:
    try:
        size = parse_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if not isinstance(size, tuple):
        raise argparse.ArgumentTypeError(f"--size expects WxH (e.g. 1280x800), use --{size} instead of {value!r}")
    return size


def gui_from_env() -> Optional[str]:
    """Backend requested by ``INTERACTIVE_PIPE_GUI``, or None when unset/empty.

    "none" is normalized to "headless".

    Raises:
        ValueError: If the variable holds an unknown backend name.
    """
    raw = os.environ.get(GUI_ENV_VAR, "").strip().lower()
    if not raw:
        return None
    if raw in _HEADLESS_ALIASES:
        return "headless"
    if raw not in GUI_CHOICES:
        raise ValueError(
            f"{GUI_ENV_VAR}={raw!r} is not a valid backend, expected one of {', '.join(GUI_CHOICES + ('none',))}"
        )
    return raw


def size_from_env() -> Optional[SizeType]:
    """Window size requested by ``INTERACTIVE_PIPE_SIZE``, or None when unset/empty.

    Raises:
        ValueError: If the variable holds an invalid size.
    """
    raw = os.environ.get(SIZE_ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        return parse_size(raw)
    except ValueError as exc:
        raise ValueError(f"{SIZE_ENV_VAR}: {exc}") from exc


def resolve_gui(gui: Any) -> Any:
    """Apply the ``INTERACTIVE_PIPE_GUI`` override to a ``gui`` decorator argument.

    Only ``"auto"`` (or ``Backend.AUTO``) is overridden; explicit backends and
    ``None`` (headless) are returned unchanged. ``"headless"`` from the
    environment is returned as None.
    """
    if not (isinstance(gui, str) and gui == "auto"):
        return gui
    env_gui = gui_from_env()
    if env_gui is None:
        return gui
    return None if env_gui == "headless" else env_gui


def add_gui_arguments(
    parser: argparse.ArgumentParser, *, defaults: Optional[Dict[str, Any]] = None
) -> argparse._ArgumentGroup:
    """Add ``--gui``, ``--fullscreen``, ``--maximized``, ``--size WxH`` and ``--name`` to a parser.

    Args:
        parser: Parser to extend.
        defaults: Optional default values, keyed by destination
            (``gui``, ``fullscreen``, ``maximized``, ``size``, ``name``).
            A default set here is always reported by ``gui_kwargs_from_args``.

    Returns:
        The argument group holding the GUI options.
    """
    if defaults is None:
        defaults = {}
    unknown = set(defaults) - {"gui", "fullscreen", "maximized", "size", "name"}
    if unknown:
        raise ValueError(f"unknown GUI argument defaults: {sorted(unknown)}")
    group = parser.add_argument_group("GUI", "interactive_pipe backend and window options")
    group.add_argument(
        "--gui",
        choices=GUI_CHOICES,
        default=defaults.get("gui"),
        help="GUI backend (default: auto, or $%s)" % GUI_ENV_VAR,
    )
    window = group.add_mutually_exclusive_group()
    window.add_argument(
        "--fullscreen",
        action="store_true",
        default=defaults.get("fullscreen", False),
        help="open the window in fullscreen",
    )
    window.add_argument(
        "--maximized",
        action="store_true",
        default=defaults.get("maximized", False),
        help="open the window maximized",
    )
    default_size = defaults.get("size")
    if isinstance(default_size, str):
        default_size = _argparse_size(default_size)
    window.add_argument(
        "--size",
        type=_argparse_size,
        default=default_size,
        metavar="WxH",
        help="window size in pixels, e.g. 1280x800",
    )
    group.add_argument("--name", default=defaults.get("name"), help="window title")
    return group


def gui_kwargs_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    """Keyword arguments for ``interactive_pipeline(**kwargs)`` from parsed arguments.

    Only options that were given (or have a default) are included, so an empty
    command line yields ``{}`` and keeps the decorator defaults
    (and the environment overrides). ``--gui headless`` maps to ``gui=None``.
    """
    kwargs: Dict[str, Any] = {}
    gui = getattr(args, "gui", None)
    if gui is not None:
        kwargs["gui"] = None if gui == "headless" else gui
    if getattr(args, "fullscreen", False):
        kwargs["size"] = "fullscreen"
    elif getattr(args, "maximized", False):
        kwargs["size"] = "maximized"
    elif getattr(args, "size", None) is not None:
        kwargs["size"] = tuple(args.size)
    name = getattr(args, "name", None)
    if name is not None:
        kwargs["name"] = name
    return kwargs


def parse_gui_args(
    argv: Optional[Sequence[str]] = None, parser: Optional[argparse.ArgumentParser] = None
) -> Tuple[argparse.Namespace, Dict[str, Any]]:
    """Parse the command line and return ``(args, gui_kwargs)``.

    Args:
        argv: Arguments to parse (defaults to ``sys.argv[1:]``).
        parser: Your own parser to extend with the GUI options; a new one is
            created when omitted.

    Returns:
        The parsed namespace and the keyword arguments for ``interactive_pipeline``.
    """
    if parser is None:
        parser = argparse.ArgumentParser()
    add_gui_arguments(parser)
    argv_list: Optional[List[str]] = list(argv) if argv is not None else None
    args = parser.parse_args(argv_list)
    return args, gui_kwargs_from_args(args)
