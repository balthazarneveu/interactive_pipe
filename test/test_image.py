
import pytest
from pathlib import Path
import numpy as np
import shutil

from interactive_pipe.data_objects.image import Image, IMAGE_BACKENDS


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
    np.testing.assert_allclose(loaded_data, data, atol=1/255)
