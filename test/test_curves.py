import numpy as np
import pytest

from interactive_pipe.data_objects.curves import Curve, SingleCurve


def test_curve_abbreviations():
    absciss = np.linspace(-1.0, 1.5, 25)
    absciss_2 = np.linspace(-3.0, -1.5, 60)
    _sig = Curve([np.cos(5.0 * absciss), np.sin(5.0 * absciss), np.tan(5.0 * absciss)])
    _sig = Curve(np.cos(5.0 * absciss))
    _sig = Curve({"y": np.log(8.0 * np.abs(absciss_2 / 10.0)), "style": "m-.", "label": "log"})
    with pytest.raises(ValueError):  # wrong sizes
        _sig = Curve(
            [
                (absciss, absciss_2),
            ]
        )  # wrong sizes

    # list of list OK
    _sig = Curve([[absciss, 3.0 * absciss + 1.0, "r-", "linear 3x+1"]])
    with pytest.raises(ValueError):  # missing list, sort of too short
        # missing list, sort of too short
        _sig = Curve([absciss, 3.0 * absciss + 1.0, "r-", "linear 3x+1"])
    _sig


def test_curves(tmp_path):
    """Create quite complex curves from some far fetched abbreviations
    Save the whole curves objects to pkl, reload it.

    """
    # Initiate a complex multi curve
    absciss = np.linspace(-1.0, 1.5, 25)
    absciss_2 = np.linspace(-3.0, -1.5, 60)
    sample_curve_path = tmp_path / "sample_curve.pkl"
    sample_curve = SingleCurve(
        absciss,
        np.tan(5.0 * absciss),
        label="tan",
        alpha=0.9,
    )
    sample_curve.x += 0.8
    sample_curve.style = "c+"
    sample_curve.save(sample_curve_path)

    sig = Curve(
        [
            (None, np.cos(5.0 * absciss), "r-o", "cos(5)"),
            [absciss_2, np.sin(5.0 * absciss_2), "k--", "sin(5)"],
            [absciss_2, np.sin(8.0 * absciss_2), None, "sin(8)"],
            [
                absciss_2 + 2.0,
                3.0 + np.sin(absciss_2 + 2.0),
                {"markersize": 10, "style": "go", "alpha": 0.2, "label": "shifted"},
            ],
            SingleCurve(
                absciss,
                np.exp(5.0 * absciss),
                label="exp",
                alpha=0.9,
            ),
            SingleCurve.from_file(sample_curve_path),
            {
                "y": np.log(8.0 * np.abs(absciss_2[:5] / 10.0)),
                "style": "m-.",
                "label": "log",
            },
        ],
        title="plot from abbreviations",
        ylim=(-5, 5),
        grid=True,
    )
    path = tmp_path / "test_curves.png"
    sig.save(path)
    # sig.show()

    # Check that the file was created
    assert path.is_file()

    # Reload from a pickle
    path = tmp_path / "test_curves.pkl"
    sig.save(path)
    assert path.is_file()

    new_sig = Curve.from_file(path)
    # new_sig.title ="reloaded
    for idx, curve in enumerate(new_sig.curves):
        assert np.isclose(curve.y, sig.curves[idx].y).all()


def test_single_curve_saves_figure(tmp_path):
    """SingleCurve.save to an image went through Curve.save_figure with the wrong
    data dict (KeyError 'curves') and never matched '.jpg'."""
    absciss = np.linspace(0.0, 1.0, 10)
    curve = SingleCurve(absciss, absciss**2, label="square")
    for suffix in (".png", ".jpg"):
        path = tmp_path / f"single{suffix}"
        curve.save(path)
        assert path.exists() and path.stat().st_size > 0


def test_curve_slice_assignment_bounds():
    absciss = np.linspace(0.0, 1.0, 10)
    crv = Curve([SingleCurve(absciss, absciss), SingleCurve(absciss, 2 * absciss)])
    crv[0:2] = [SingleCurve(absciss, 3 * absciss), SingleCurve(absciss, 4 * absciss)]
    np.testing.assert_allclose(crv[1].y, 4 * absciss)
    with pytest.raises(ValueError):
        crv[0:2] = [SingleCurve(absciss, absciss)]
    with pytest.raises(TypeError):
        crv[0:1] = ["not a curve"]


def test_curve_update_plot_handles_curve_count_change():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    absciss = np.linspace(0.0, 1.0, 10)
    fig, ax = plt.subplots()
    crv = Curve([SingleCurve(absciss, absciss, label="a")])
    plt_obj = crv.create_plot(ax=ax)
    assert len(ax.get_lines()) == 1
    # more curves than before: the plot is rebuilt
    crv.append(SingleCurve(absciss, 2 * absciss, label="b"))
    plt_obj = crv.update_plot(plt_obj, ax=ax)
    assert len(plt_obj) == 2 and len(ax.get_lines()) == 2
    # same count but a different signal length (x omitted): no size mismatch
    crv[0] = SingleCurve(y=np.linspace(0.0, 1.0, 20))
    plt_obj = crv.update_plot(plt_obj, ax=ax)
    assert len(ax.get_lines()[0].get_xdata()) == 20
    plt.close(fig)
