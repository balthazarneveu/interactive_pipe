"""Errors raised while building a control widget name the control.

The widget factories check their invariants with messages such as
``Expected int control type, got <class 'float'>``; ``name_control_errors``
wraps a factory class's ``check_control_type`` / ``create`` so that a
``TypeError`` / ``ValueError`` they raise starts with the control (and the
filter it belongs to): ``control 'gain' (filter 'amplify'): Expected int
control type, got <class 'float'>``. Used by ``BaseControl.__init_subclass__``
of the Gradio and notebook factories: one hook instead of an edit per message.
"""

import functools
from typing import Any, Callable

WRAPPED_METHODS = ("check_control_type", "create")


def control_label(widget: Any) -> str:
    """``control 'gain' (filter 'amplify')`` for a widget wrapper with ``name`` / ``ctrl``."""
    ctrl = getattr(widget, "ctrl", None)
    name = getattr(widget, "name", None) or getattr(ctrl, "name", None)
    label = f"control {name!r}"
    filter_name = getattr(getattr(ctrl, "filter_to_connect", None), "name", None)
    if filter_name:
        label += f" (filter {filter_name!r})"
    return label


def _named(method: Callable) -> Callable:
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (TypeError, ValueError) as error:
            label = control_label(self)
            if str(error).startswith(label):
                raise
            raise type(error)(f"{label}: {error}") from error

    wrapper.__wrapped_control_errors__ = True  # type: ignore[attr-defined]
    return wrapper


def name_control_errors(cls: type) -> None:
    """Wrap the checking / building methods defined by `cls` (see module docstring)."""
    for method_name in WRAPPED_METHODS:
        method = cls.__dict__.get(method_name)
        if callable(method) and not getattr(method, "__wrapped_control_errors__", False):
            setattr(cls, method_name, _named(method))
