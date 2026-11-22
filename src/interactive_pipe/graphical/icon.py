"""Window / tab icon shared by the GUI backends (the pipe logo, without the text)."""

from pathlib import Path
from typing import Optional

_ASSETS = Path(__file__).parent / "assets"


def icon_path(kind: str = "png") -> Optional[str]:
    """Path of the packaged icon (``"png"`` or ``"ico"``), or None if it is missing."""
    path = _ASSETS / f"icon.{kind}"
    return str(path) if path.is_file() else None
