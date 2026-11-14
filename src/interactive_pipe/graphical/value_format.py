"""How a control value is written next to its widget, on every backend and in
snapshot captions: like a person would write it.

``6.0`` -> ``6``, ``0.1`` -> ``0.1``, ``0.005`` -> ``0.005``, ``20000.0`` ->
``20000``, ``1/3`` -> ``0.3333`` (4 significant digits), ``1e-05`` and
``1.5e+07`` in scientific notation only outside ``[1e-4, 1e6)``.

Each backend calls one function of this module (a sibling branch changes the
control widgets themselves):

- ``format_number`` / ``format_value``: Python text (Qt, matplotlib,
  snapshot captions);
- ``printf_format``: the printf format giving the same text, for widgets
  formatting the value natively (Dear PyGui);
- ``D3_FORMAT``: the closest d3-format ipywidgets accepts (trailing zeros
  trimmed; 6 significant digits, so ``0.333333`` for 1/3);
- ``JS_FORMAT_NUMBER``: ``format_number`` in JavaScript (Gradio's custom range
  slider).
"""

import math
from typing import Any

SIGNIFICANT_DIGITS = 4
POSITIONAL_RANGE = (1e-4, 1e6)  # outside: scientific notation

# ipywidgets' readout_format (d3-format, no type: like "g" with trailing zeros
# trimmed; ipywidgets refuses the "~" flag). 6 significant digits so that
# 20000 stays "20000" (4 would give "2e+4"): 1/3 shows as 0.333333 there.
D3_FORMAT = ".6"

# format_number in JavaScript: `fmt(v)` returns the same text
JS_FORMAT_NUMBER = (
    "const fmt = (v) => { v = Number(v); const a = Math.abs(v); if (v === 0 || !isFinite(v)) return String(v);"
    " if (a >= 1e-4 && a < 1e6) { const d = Math.max(0, 3 - Math.floor(Math.log10(a)));"
    " return String(Number(v.toFixed(d))); }"
    " return v.toExponential(2).replace(/\\.?0+e/, 'e').replace(/e([+-])(\\d)$/, 'e$10$2'); };"
)


def _decimals(value: float) -> int:
    """Decimals of `value` written with SIGNIFICANT_DIGITS digits, trailing zeros dropped."""
    exponent = math.floor(math.log10(abs(value)))
    decimals = max(0, SIGNIFICANT_DIGITS - 1 - exponent)
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0")
        return len(text) - text.index(".") - 1
    return 0


def _positional(value: float) -> bool:
    return POSITIONAL_RANGE[0] <= abs(value) < POSITIONAL_RANGE[1]


def printf_format(value: float) -> str:
    """printf format writing `value` as ``format_number`` does (``%.2f``, ``%.3g``...)."""
    value = float(value)
    if value == 0 or not math.isfinite(value):
        return "%g"
    if _positional(value):
        return f"%.{_decimals(value)}f"
    return f"%.{SIGNIFICANT_DIGITS - 1}g"


def format_number(value: Any) -> str:
    """A number as a person would write it (see the module docstring)."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int) or (hasattr(value, "dtype") and getattr(value.dtype, "kind", "") in "iu"):
        return str(int(value))
    value = float(value)
    text = printf_format(value) % value
    return "0" if text in ("-0", "-0.0") else text


def format_value(value: Any) -> str:
    """Any parameter value, short: numbers via ``format_number``, tuples as
    ``(a, b)`` (ranges, points), lists as ``[a, b]``, arrays as ``array(H, W)``,
    other objects as a repr cut at 40 characters. Used next to the Qt widgets,
    in snapshot captions, sweep labels, ``describe`` / ``check`` and warnings."""
    import numpy as np

    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, float, np.integer, np.floating)):
        return format_number(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (tuple, list)):
        inner = ", ".join(format_value(item) for item in value)
        return f"({inner})" if isinstance(value, tuple) else f"[{inner}]"
    if isinstance(value, np.ndarray):
        return f"array{value.shape}"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."
