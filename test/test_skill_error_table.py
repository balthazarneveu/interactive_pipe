"""The "Errors and fixes" table of the agent skill quotes the messages the library really gives.

Each row's message is split on `...`; every piece must appear in the real
message of the matching mistake (run here)."""

import logging
import re
from pathlib import Path

import numpy as np
import pytest

from interactive_pipe import interactive, interactive_pipeline, layout

SKILL = Path(__file__).resolve().parent.parent / "src" / "interactive_pipe" / "agent" / "build-interactive-pipeline"


def _table_messages():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    table = text[text.index("| Message | Fix |") : text.index("## More")]
    rows = [line for line in table.splitlines()[2:] if line.startswith("| ")]
    messages = []
    for row in rows:
        cell = row[2 : row.index(" | ", 2)]
        spans = re.findall(r"`(.+?)`(?=\s*(?:\+|$))", cell) or re.findall(r"`(.+)`", cell)
        if spans:
            messages.append(spans[0])
    return messages


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(img, gain=1.0):
    return img * gain


def _syntax():
    @interactive_pipeline(gui=None)
    def p(img):
        if img:
            pass
        return img


def _unknown_name():
    @interactive_pipeline(gui=None)
    def p(img):
        out = amplify(img)
        return out

    p(np.zeros((4, 4)), gian=2)


def _bare_value():
    @interactive(gain=1.0)
    def f(img, gain=1.0):
        return img


def _default_outside():
    @interactive(gain=(5, [0, 3]))
    def f(img, gain=1.0):
        return img


def _filter_error():
    @interactive()
    def f(img):
        raise ValueError("bad")

    @interactive_pipeline(gui=None)
    def p(img):
        out = f(img)
        return out

    p(np.zeros(3))


def _returned_values():
    @interactive()
    def f(img):
        return [1, 2, 3]

    @interactive_pipeline(gui=None)
    def p(img):
        out = f(img)
        return out

    p(np.zeros(3))


def _display_error():
    @interactive()
    def f(img):
        return np.zeros((3, 8, 8))

    @interactive_pipeline(gui=None)
    def p(img):
        out = f(img)
        return out

    p.snapshot(None, np.zeros(3))


def _outside_filter():
    layout.style("x", title="y")


def _clamped(caplog):
    @interactive_pipeline(gui=None)
    def p(img):
        out = amplify(img)
        return out

    with pytest.warns(UserWarning):
        p.snapshot(None, np.zeros((4, 4)), gain=9)


def _misleading(caplog):
    @interactive()
    def ints(img):
        return (img * 255).astype(np.int64)

    @interactive_pipeline(gui=None)
    def p(img):
        out = ints(img)
        return out

    p.snapshot(None, np.full((4, 4), 0.5))


RAISING = {
    "PipelineSyntaxError": _syntax,
    "got unexpected keyword argument": _unknown_name,
    "a bare value cannot make a widget": _bare_value,
    "is outside the range [0, 3]": _default_outside,
    "FilterError": _filter_error,
    "returned 3 values": _returned_values,
    "DisplayError": _display_error,
    "outside of filter execution": _outside_filter,
}
LOGGED = {"clamped to": _clamped, "displayed misleadingly": _misleading}


def _mistake_for(message):
    for key, mistake in {**RAISING, **LOGGED}.items():
        if key in message:
            return key, mistake
    return None, None


@pytest.mark.parametrize("message", _table_messages())
def test_documented_message_is_the_real_one(message, caplog):
    key, mistake = _mistake_for(message)
    if mistake is None:
        assert not message.startswith(("ValueError", "TypeError", "RuntimeError")), f"no reproducer for {message!r}"
        return
    if key in LOGGED:
        with caplog.at_level(logging.WARNING):
            mistake(caplog)
        real = "\n".join(record.getMessage() for record in caplog.records)
        message = message.removeprefix("Log ")
    else:
        with pytest.raises(Exception) as info:
            mistake()
        real = f"{type(info.value).__name__}: {info.value}"
    real = " ".join(real.split())
    for piece in message.split("..."):
        assert re.search(_pattern(piece.strip(" .")), real), f"{piece!r} not in {real!r}"


def _pattern(piece):
    """Placeholders of the table: `file.py`, `line N`, and a filter 'f' defined in a test function."""
    pattern = re.escape(piece)
    pattern = pattern.replace(re.escape("file.py"), r".+?").replace(re.escape("line N"), r"line \d+")
    return pattern.replace(re.escape("filter 'f'"), r"filter '(?:[\w.<>]+\.)?f'")


def test_every_raising_mistake_is_documented():
    messages = _table_messages()
    for key in [*RAISING, *LOGGED]:
        assert any(key in message for message in messages), key
