"""HeadlessPipeline.save writes every supported output type."""

import logging

import numpy as np

from interactive_pipe import Curve, Table, interactive
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.table import PANDAS_AVAILABLE
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive()
def to_gray(img):
    return img.mean(axis=-1)


@interactive()
def to_uint8(img):
    return (img * 255).astype(np.uint8)


@interactive()
def profile(img):
    return img[0, :, 0]


@interactive()
def volume(img):
    return np.stack([img] * 2)


@interactive()
def as_curve(img):
    return Curve([np.arange(4), np.arange(4) ** 2])


@interactive()
def as_table(img):
    return Table({"a": [1, 2], "b": [3, 4]})


@interactive()
def as_text(img):
    return "hello"


@interactive()
def as_dict(img):
    return {"not": "saveable"}


def save_pipeline(img):
    gray = to_gray(img)
    bytes_img = to_uint8(img)
    line = profile(img)
    vol = volume(img)
    curve = as_curve(img)
    table = as_table(img)
    text = as_text(img)
    meta = as_dict(img)
    return [[img, gray, bytes_img], [line, vol, curve], [table, text, meta]]


def test_save_writes_each_output_in_a_matching_format(tmp_path, caplog):
    pipe = HeadlessPipeline.from_function(save_pipeline)
    pipe(np.full((4, 6, 3), 0.5))
    with caplog.at_level(logging.WARNING):
        written = pipe.save(tmp_path / "out.png")
    names = sorted(p.name for p in written)
    assert names == sorted(
        [
            "out_img.png",
            "out_gray.png",
            "out_bytes_img.png",
            "out_line.csv",
            "out_vol.npy",
            "out_curve.png",
            # without pandas (the CI installs only the [pytest] extra) a Table is pickled
            "out_table.csv" if PANDAS_AVAILABLE else "out_table.pkl",
            "out_text.txt",
        ]
    )
    for written_path in written:
        assert written_path.is_file()
    assert (tmp_path / "out.yaml").is_file()  # tuning
    np.testing.assert_allclose(Image.load_image(tmp_path / "out_gray.png")[..., 0], 0.5, atol=1 / 255)
    np.testing.assert_allclose(Image.load_image(tmp_path / "out_bytes_img.png"), 127 / 255, atol=1 / 255)
    assert (tmp_path / "out_text.txt").read_text() == "hello"
    assert np.load(tmp_path / "out_vol.npy").shape == (2, 4, 6, 3)
    # one clear warning for the unsupported output, no traceback
    assert "Not saved (unsupported output type): meta (dict)" in caplog.text
    assert "Traceback" not in caplog.text
    assert not [record for record in caplog.records if record.exc_info]


@interactive()
def brighten(img, gain=2.0):
    return img * gain


def call_named_pipeline(img):
    return brighten(img)


def test_hoisted_output_names_make_portable_file_names(tmp_path):
    pipe = HeadlessPipeline.from_function(call_named_pipeline)
    pipe(np.full((4, 4, 3), 0.25))
    (written,) = pipe.save(tmp_path / "res.jpg")
    assert written.name == "res_brighten(img).jpg"
    assert written.is_file()


def test_data_wrapper_fn_is_still_honoured(tmp_path):
    pipe = HeadlessPipeline.from_function(call_named_pipeline)
    pipe(np.full((4, 4, 3), 0.25))
    (written,) = pipe.save(tmp_path / "res.png", data_wrapper_fn=lambda x: Image(x, title="_wrapped"))
    assert written.name == "res_brighten(img)_wrapped.png"
    assert written.is_file()
