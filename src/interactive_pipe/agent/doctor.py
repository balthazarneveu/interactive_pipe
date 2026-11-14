"""``interactive-pipe doctor``: why does (or doesn't) a window show up?

Reports the versions, which GUI backends can be imported (with the pip extra
to install for each missing one), whether a display is available and which
backend ``gui="auto"`` would pick. Importing a backend module creates no window
and no application object.
"""

import importlib
import logging
import os
import platform
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class BackendStatus:
    gui: str
    available: bool
    detail: str  # version found, or the import error
    install: str  # pip command enabling it


#: gui value -> (module imported to check it, pip extra, what it needs)
BACKENDS = {
    "qt": ("interactive_pipe.graphical.qt_gui", "qt6", "PyQt6, PyQt5 or PySide6"),
    "dpg": ("dearpygui.dearpygui", "dpg", "dearpygui"),
    "mpl": ("matplotlib", None, "matplotlib (a core dependency)"),
    "nb": ("ipywidgets", "notebook", "ipywidgets, in Jupyter"),
    "gradio": ("gradio", "gradio", "gradio"),
}


def _qt_binding() -> Optional[str]:
    """Name and version of the Qt binding the Qt backend uses, without importing it twice."""
    for name in ("PyQt6", "PyQt5", "PySide6"):
        module = sys.modules.get(f"{name}.QtCore")
        if module is None:
            continue
        version = getattr(module, "PYQT_VERSION_STR", None) or getattr(module, "__version__", "")
        return f"{name} {version}".strip()
    return None


def check_backend(gui: str) -> BackendStatus:
    module_name, extra, needs = BACKENDS[gui]
    install = f'pip install "interactive-pipe[{extra}]"' if extra else "pip install matplotlib"
    logging.disable(logging.WARNING)  # the Qt cascade logs every binding it misses: reported below instead
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - any import failure means "not available", reported as is
        first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return BackendStatus(gui, False, f"needs {needs}: {first_line}", install)
    finally:
        logging.disable(logging.NOTSET)
    if gui == "qt":
        detail = _qt_binding() or "Qt binding found"
    else:
        version = getattr(module, "__version__", None)
        if version is None and gui == "dpg":
            version = getattr(importlib.import_module("dearpygui"), "__version__", None)
        detail = f"{module_name.split('.')[0]} {version}" if version else module_name.split(".")[0]
    return BackendStatus(gui, True, detail, install)


def display_status() -> Dict[str, Any]:
    """Whether windows can be shown: a display server on Linux, always elsewhere."""
    system = platform.system()
    notes: List[str] = []
    if system == "Linux":
        names = [name for name in ("DISPLAY", "WAYLAND_DISPLAY") if os.environ.get(name)]
        available = bool(names)
        detail = ", ".join(f"{name}={os.environ[name]}" for name in names) if names else "no DISPLAY / WAYLAND_DISPLAY"
    else:
        available = True
        detail = f"{system} desktop assumed"
    if os.environ.get("QT_QPA_PLATFORM", "") in ("offscreen", "minimal"):
        notes.append(f"QT_QPA_PLATFORM={os.environ['QT_QPA_PLATFORM']}: Qt windows are invisible")
    if os.environ.get("MPLBACKEND", "").lower() == "agg":
        notes.append("MPLBACKEND=Agg: matplotlib windows are not shown")
    return {"available": available, "detail": detail, "notes": notes}


def _in_ipython() -> bool:
    try:
        __IPYTHON__  # type: ignore  # noqa: F821, B018
    except NameError:
        return False
    return True


def auto_choice(backends: Dict[str, BackendStatus]) -> Dict[str, str]:
    """Backend ``gui="auto"`` picks, with the reason (same order as helper/choose_backend.py)."""
    from interactive_pipe.cli import GUI_ENV_VAR, gui_from_env

    try:
        env_gui = gui_from_env()
    except ValueError as exc:
        return {"gui": "error", "reason": str(exc)}
    if env_gui is not None and env_gui != "auto":
        return {"gui": env_gui, "reason": f"{GUI_ENV_VAR}={os.environ[GUI_ENV_VAR]}"}
    if _in_ipython():
        return {"gui": "nb", "reason": "running in IPython / Jupyter"}
    for gui in ("qt", "dpg", "mpl"):
        if backends[gui].available:
            return {"gui": gui, "reason": "first importable of qt, dpg, mpl"}
    return {"gui": "none", "reason": "no backend importable"}


def diagnose() -> Dict[str, Any]:
    """Everything ``interactive-pipe doctor`` reports, as JSON-friendly data."""
    import interactive_pipe

    backends = {gui: check_backend(gui) for gui in BACKENDS}
    display = display_status()
    auto = auto_choice(backends)
    advice: List[str] = []
    if auto["gui"] in ("qt", "dpg", "mpl") and not display["available"]:
        advice.append(
            f'gui="auto" picks {auto["gui"]} but no display was found: render PNGs instead '
            "(pipe.snapshot(...), `interactive-pipe snapshot script.py`) or use gui=None (headless)"
        )
    if not backends["qt"].available:
        advice.append(f"for the richest GUI: {backends['qt'].install}")
    return {
        "interactive_pipe": {
            "version": interactive_pipe.__version__,
            "path": os.path.dirname(interactive_pipe.__file__),
        },
        "python": {"version": platform.python_version(), "executable": sys.executable, "platform": platform.platform()},
        "backends": {gui: asdict(status) for gui, status in backends.items()},
        "display": display,
        "auto": auto,
        "environment": {
            name: os.environ.get(name)
            for name in ("INTERACTIVE_PIPE_GUI", "INTERACTIVE_PIPE_SIZE", "INTERACTIVE_PIPE_SNAPSHOT")
            if os.environ.get(name)
        },
        "advice": advice,
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        f"interactive_pipe {report['interactive_pipe']['version']} ({report['interactive_pipe']['path']})",
        f"Python {report['python']['version']} ({report['python']['executable']})",
        f"Platform {report['python']['platform']}",
        "",
        "Backends (gui=...):",
    ]
    for gui, status in report["backends"].items():
        state = "ok     " if status["available"] else "missing"
        hint = "" if status["available"] else f"  -> {status['install']}"
        lines.append(f"  {gui:<7} {state} {status['detail']}{hint}")
    display = report["display"]
    lines += ["", f"Display: {'available' if display['available'] else 'NOT available'} ({display['detail']})"]
    lines += [f"  note: {note}" for note in display["notes"]]
    lines.append(f'gui="auto" picks: {report["auto"]["gui"]} ({report["auto"]["reason"]})')
    if report["environment"]:
        lines.append("Environment: " + ", ".join(f"{key}={value}" for key, value in report["environment"].items()))
    if report["advice"]:
        lines.append("")
        lines += [f"* {advice}" for advice in report["advice"]]
    return "\n".join(lines)
