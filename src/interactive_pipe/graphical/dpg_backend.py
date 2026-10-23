"""Dear PyGui import cascade and shared helpers for the ``dpg`` backend.

Importing this module raises ``ModuleNotFoundError`` when dearpygui is not
installed (choose_backend relies on that for the ``auto`` cascade).
``dpg_control`` catches the error so it stays importable without the binding;
the GUI modules import it directly.

Dear PyGui keeps one global context: ``create_context`` / ``destroy_context``
are wrapped here so callers (GUI and tests) can ask whether a context is alive
without touching the C library, which segfaults without one.
"""

from typing import Dict

try:
    import dearpygui.dearpygui as dpg
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only without dearpygui
    raise ModuleNotFoundError(
        "Dear PyGui is required for the dpg backend. Install it with: pip install 'interactive-pipe[dpg]'"
    ) from exc

from interactive_pipe.headless.keyboard import KeyboardControl

__all__ = ["dpg", "INSTALL_HINT", "context_alive", "create_context", "destroy_context", "key_code_table"]

INSTALL_HINT = "pip install 'interactive-pipe[dpg]'"

_context_alive = False


def context_alive() -> bool:
    """True once create_context() ran and destroy_context() did not."""
    return _context_alive


def create_context() -> None:
    """Create the global Dear PyGui context (no-op when one is alive)."""
    global _context_alive
    if not _context_alive:
        dpg.create_context()
        _context_alive = True


def destroy_context() -> None:
    """Destroy the global Dear PyGui context (no-op when none is alive)."""
    global _context_alive
    if _context_alive:
        dpg.destroy_context()
        _context_alive = False


def key_code_table() -> Dict[int, str]:
    """Map Dear PyGui key codes to the key names used by InteractivePipeGUI.

    Letters map to their lowercase character, digits to the digit, the
    special keys to the ``KeyboardControl`` names ("up", "pageup", " ", ...)
    and the function keys to "f1".."f12".
    """
    table: Dict[int, str] = {}
    for letter in "abcdefghijklmnopqrstuvwxyz":
        table[getattr(dpg, f"mvKey_{letter.upper()}")] = letter
    for digit in "0123456789":
        table[getattr(dpg, f"mvKey_{digit}")] = digit
    for index in range(1, 13):
        table[getattr(dpg, f"mvKey_F{index}")] = f"f{index}"
    table.update(
        {
            dpg.mvKey_Up: KeyboardControl.KEY_UP,
            dpg.mvKey_Down: KeyboardControl.KEY_DOWN,
            dpg.mvKey_Left: KeyboardControl.KEY_LEFT,
            dpg.mvKey_Right: KeyboardControl.KEY_RIGHT,
            dpg.mvKey_Prior: KeyboardControl.KEY_PAGEUP,
            dpg.mvKey_Next: KeyboardControl.KEY_PAGEDOWN,
            dpg.mvKey_Spacebar: KeyboardControl.KEY_SPACEBAR,
        }
    )
    return table
