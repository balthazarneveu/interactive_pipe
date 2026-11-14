"""Every public name of interactive_pipe has a page entry in docs/api/."""

from pathlib import Path

import interactive_pipe

API = Path(__file__).resolve().parent.parent / "docs" / "api"
# documented elsewhere: aliases, proxies (context.md documents their classes), the version
NOT_ON_API_PAGES = {"__version__", "block", "pipeline", "context", "layout", "audio", "events"}


def test_every_public_name_is_on_an_api_page():
    pages = "\n".join(path.read_text(encoding="utf-8") for path in API.glob("*.md"))
    missing = [
        name
        for name in interactive_pipe.__all__
        if name not in NOT_ON_API_PAGES
        and f"::: interactive_pipe.{name}" not in pages
        and f".{name}\n" not in pages  # documented under its module path
    ]
    assert missing == []
