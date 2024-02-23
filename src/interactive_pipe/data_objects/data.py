from pathlib import Path
from typing import Optional, Any
from abc import abstractmethod
import pickle


class Data:
    def __init__(self, data, **kwargs) -> None:
        self._set_file_extensions()
        if isinstance(data, Path):
            # you can directly instantiate from a Path - similar to from_file
            self.data = self.load(data)
        elif data is None:
            pass
        else:
            self.data = data

    @classmethod
    def from_file(cls, path=None, **kwargs):
        if isinstance(path, str):
            path = Path(path)
        assert path is None or isinstance(path, Path), "not a path or None"
        data_class = cls(None)
        data_class.load(path, **kwargs)
        return data_class

    @property
    def file_extensions(self):
        return self._file_extensions

    @file_extensions.setter
    def file_extensions(self, new_file_extensions):
        if isinstance(new_file_extensions, str):
            self._file_extensions = [new_file_extensions]
        else:
            self._file_extensions = new_file_extensions
        assert self._file_extensions is None or isinstance(
            self._file_extensions, list)
        if isinstance(self._file_extensions, list):
            for el in self._file_extensions:
                assert isinstance(el, str)
                assert el.startswith(".")

    @abstractmethod
    def _set_file_extensions(self):
        self.file_extensions = None
        pass

    @abstractmethod
    def _save(self, path: Path, **kwargs):
        pass

    @abstractmethod
    def _load(self, path: Path, **kwargs) -> Any:
        pass

    def save(self, path: Path = None, override=True, **kwargs):
        path = self.check_path(
            path if (override or path is None) else self.safe_path_with_suffix(
                path),
            extensions=self.file_extensions
        )
        self._save(path, **kwargs)

    def load(self, path: Path = None, **kwargs):
        path = self.check_path(
            path, load=True, extensions=self.file_extensions)
        self.data = self._load(path, **kwargs)
        return self.data

    @staticmethod
    def prompt_file(message="Please enter a file path: ") -> str:
        return input(message)

    @staticmethod
    def check_path(path: Optional[Path] = None, load: bool = False, extensions=None) -> Path:
        if path is None:
            path = Data.prompt_file()
        assert path is not None
        if isinstance(path, str):
            path = Path(path)
        assert isinstance(path, Path)
        if load:  # loading
            assert path.exists()
            if extensions is not None:
                assert path.suffix in extensions, f"{path.suffix} shall be among {extensions}"
            return path
        else:  # saving
            if not path.parent.exists():
                path.parent.mkdir(exist_ok=True, parents=True)
            if extensions is not None:
                if path.suffix not in extensions:
                    path = path.with_suffix(extensions[0])
                    print("path modified to default extension!", path)
            return path

    @staticmethod
    def safe_path_with_suffix(path: Path) -> Path:
        # Protect against overwritting an existing file
        assert path is not None
        if isinstance(path, str):
            path = Path(path)
        idx = 1
        orig_path = path
        while path.is_file():
            path = orig_path.with_name('%s_%d%s' % (
                orig_path.stem, idx, orig_path.suffix))
            idx += 1
        return path

    @staticmethod
    def append_with_stem(path, extra):
        return path.parent/(path.stem + extra + path.suffix)

    @staticmethod
    def save_binary(data, path: Path):
        assert path.suffix == ".pkl"
        with open(path, 'wb') as handle:
            pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load_binary(path: Path):
        with open(path, 'rb') as handle:
            data = pickle.load(handle)
        return data
