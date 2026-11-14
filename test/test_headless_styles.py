"""HeadlessPipeline.styles: titles / styles set by filters, readable in tests."""

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from interactive_pipe import interactive, interactive_pipeline, layout  # noqa: E402


@interactive()
def measure(img, gain=1.0):
    out = img * gain
    layout.style("out", title=f"mean {out.mean():.2f}", colormap="viridis")
    return out


@interactive_pipeline(gui="mpl")  # any GUI pipeline; matplotlib is always installed, Qt is not on CI
def styled(img):
    out = measure(img)
    return out


def test_styles_of_the_last_run_on_the_headless_twin():
    img = np.ones((4, 4))
    styled.headless(img, gain=2.0)
    assert styled.headless.styles["out"] == {"title": "mean 2.00", "colormap": "viridis"}
    styled.headless(img, gain=3.0)
    assert styled.headless.styles["out"]["title"] == "mean 3.00"


def test_styles_is_a_copy_and_unstyled_outputs_are_absent():
    styled.headless(np.ones((2, 2)), gain=1.0)
    styles = styled.headless.styles
    styles["out"]["title"] = "changed"
    assert styled.headless.styles["out"]["title"] == "mean 1.00"
    assert "img" not in styles
