"""The examples page lists every demo script, the readme stays short and its links resolve."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "docs" / "guide" / "examples.md"
README = ROOT / "readme.md"


def test_every_demo_is_on_the_examples_page():
    text = EXAMPLES.read_text(encoding="utf-8")
    scripts = sorted(path.name for path in (ROOT / "demo").glob("*.py"))
    gallery = (ROOT / "demo" / "gallery").glob("*.py")
    scripts += sorted(path.name for path in gallery)
    missing = [name for name in scripts if f"`{name}`" not in text and f"`{name.removesuffix('.py')}.py`" not in text]
    assert not missing, f"not on docs/guide/examples.md: {missing}"


def test_images_of_the_examples_page_and_readme_exist():
    for page, base in ((EXAMPLES, EXAMPLES.parent), (README, ROOT)):
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", page.read_text(encoding="utf-8")):
            if not target.startswith("http"):
                assert (base / target).is_file(), f"{page.name}: missing image {target}"


def test_readme_feature_list():
    text = README.read_text(encoding="utf-8")
    features = text[text.index("## Features") : text.index("## Backends")]
    for topic in (
        "snapshot",
        "sweep",
        "type hints",
        "Figure",
        "overlays",
        "Mouse input",
        "interactive-pipe check",
        "skill",
    ):
        assert topic in features, topic
    assert features.count("![") <= 1  # one image at most
    assert len(text.splitlines()) < 110  # the first page people see: keep it short


def test_readme_demo_count():
    count = len(list((ROOT / "demo").glob("*.py")))
    assert f"{count} demo scripts" in README.read_text(encoding="utf-8")
