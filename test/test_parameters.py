import pytest
from pathlib import Path
import shutil

from interactive_pipe.data_objects.parameters import Parameters

SAMPLE_DICT = {"key1": 25, "key2": {"key_2_1": 1,
                                    "key_2_2": True}, "key_3": [True, 1.256664, False]}


@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_save(tmp_path, extension):
    params = Parameters(SAMPLE_DICT)
    file_path = tmp_path / f"test.{extension}"
    params.save(str(file_path))
    assert file_path.is_file()
    params_reloaded = Parameters(file_path)
    assert params_reloaded.data == SAMPLE_DICT
    assert Parameters.from_file(file_path).data == SAMPLE_DICT


def test_invalid_file_extension(tmp_path):
    file_path = tmp_path/"fake.txt"
    if file_path.exists():
        file_path.unlink()
    with pytest.raises(AssertionError):
        params = Parameters.from_file(file_path)
    file_path.write_text("fake")
    with pytest.raises(AssertionError):
        params = Parameters.from_file(file_path)
