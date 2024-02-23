
import pytest
import numpy as np

from interactive_pipe.data_objects.curves import Curve, SingleCurve


def test_curve_abbreviations():
    absciss = np.linspace(-1., 1.5, 25)
    absciss_2 = np.linspace(-3., -1.5, 60)
    _sig = Curve([np.cos(5.*absciss), np.sin(5.*absciss), np.tan(5.*absciss)])
    _sig = Curve(np.cos(5.*absciss))
    _sig = Curve({"y": np.log(8.*np.abs(absciss_2/10.)),
                  "style": "m-.", "label": "log"})
    with pytest.raises(AssertionError):
        _sig = Curve([(absciss, absciss_2),])  # wrong sizes

    # list of list OK
    _sig = Curve([[absciss, 3.*absciss+1., "r-", "linear 3x+1"]])
    with pytest.raises(AssertionError):
        # missing list, sort of too short
        _sig = Curve([absciss, 3.*absciss+1., "r-", "linear 3x+1"])


def test_curves(tmp_path):
    """Create quite complex curves from some far fetched abbreviations
    Save the whole curves objects to pkl, reload it.

    """
    # Initiate a complex multi curve
    absciss = np.linspace(-1., 1.5, 25)
    absciss_2 = np.linspace(-3., -1.5, 60)
    sample_curve_path = tmp_path / "sample_curve.pkl"
    sample_curve = SingleCurve(
        absciss,
        np.tan(5.*absciss),
        label="tan",
        alpha=0.9,
    )
    sample_curve.x += 0.8
    sample_curve.style = "c+"
    sample_curve.save(sample_curve_path)

    sig = Curve(
        [
            (None, np.cos(5.*absciss), "r-o", "cos(5)"),
            [absciss_2, np.sin(5.*absciss_2), "k--", "sin(5)"],
            [absciss_2, np.sin(8.*absciss_2), None, "sin(8)"],
            [absciss_2+2., 3.+np.sin(absciss_2+2.), {
                "markersize": 10, "style": "go", "alpha": 0.2,
                "label": "shifted"}],
            SingleCurve(
                absciss,
                np.exp(5.*absciss),
                label="exp",
                alpha=0.9,
            ),
            SingleCurve.from_file(sample_curve_path),
            {"y": np.log(8.*np.abs(absciss_2[:5]/10.)),
             "style": "m-.", "label": "log"}
        ],
        title="plot from abbreviations",
        ylim=(-5, 5),
        grid=True
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
