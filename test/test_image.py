import numpy as np
import pytest

from interactive_pipe.data_objects.image import IMAGE_BACKENDS, Image


@pytest.mark.parametrize("backend_load", IMAGE_BACKENDS)
@pytest.mark.parametrize("backend_save", IMAGE_BACKENDS)
def test_save_load(tmp_path, backend_load, backend_save):
    # Create a sample image as a numpy array
    data = np.random.rand(100, 100, 3)
    path = tmp_path / f"test_{backend_save}.png"
    Image.save_image(data, path, precision=8, backend=backend_save)

    # Check that the file was created
    assert path.is_file()

    # Load the image and check that the data is as expected
    loaded_data = Image.from_file(path, backend=backend_load).data
    # allow for slight differences
    np.testing.assert_allclose(loaded_data, data, atol=1 / 255)


@pytest.mark.parametrize("backend", ["pillow", "opencv"])
def test_rgba_round_trip(tmp_path, backend):
    from interactive_pipe.data_objects.image import image_backends

    if backend not in image_backends:
        pytest.skip(f"{backend} not installed")
    rgba = np.zeros((4, 5, 4))
    rgba[..., 0] = 1.0  # red
    rgba[..., 3] = np.linspace(0.0, 1.0, 5)[None, :]  # alpha ramp
    path = tmp_path / "rgba.png"
    Image.save_image(rgba, path, backend=backend)
    loaded = Image.load_image(path, backend=backend)
    assert loaded.shape == (4, 5, 4)
    np.testing.assert_allclose(loaded, np.round(rgba * 255) / 255, atol=1e-6)


def test_wrong_channel_count_raises(tmp_path):
    with pytest.raises(ValueError, match="RGB or RGBA"):
        Image.save_image(np.zeros((4, 4, 2)), tmp_path / "bad.png")
