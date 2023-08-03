
import pytest
from pathlib import Path
import numpy as np
import shutil

try:
    from interactive_pipe.data_objects.image import Image, IMAGE_BACKENDS
except:
    import helper
    from data_objects.image import Image, IMAGE_BACKENDS

@pytest.mark.parametrize("backend", IMAGE_BACKENDS)
def test_save_load(tmp_path, backend):
    # Create a sample image as a numpy array
    data = np.random.rand(100, 100, 3)
    path = tmp_path / f"test_{backend}.png"
    Image.save_image(data, path, precision=8, backend=backend)

    # Check that the file was created
    assert path.is_file()

    # Load the image and check that the data is as expected
    loaded_data = Image.from_file(path).data
    np.testing.assert_allclose(loaded_data, data, atol=1/255)  # allow for slight differences