from interactive_pipe.data_objects.data import Data
from pathlib import Path
import logging
import json
YAML_SUPPORT = True
YAML_NOT_DETECTED_MESSAGE = "yaml is not installed, consider installing it by pip install PyYAML"
try:
    import yaml
    from yaml.loader import SafeLoader
except:
    YAML_SUPPORT = False
    logging.warning(YAML_NOT_DETECTED_MESSAGE)


class Parameters(Data):
    def _set_file_extensions(self):
        self.file_extensions = ['.json']
        if YAML_SUPPORT:
            self.file_extensions.append(".yaml")

    def _load(self, path: Path):
        assert path.suffix in self.file_extensions, f"Unsupported file extension: {path.suffix}, {self.file_extensions}"
        if path.suffix == '.json':
            params = self.load_json(path)
        elif path.suffix == '.yaml':
            params = self.load_yaml(path)
        else:
            raise NotImplementedError(path.suffix)
        return params

    def _save(self, path: Path):
        assert path.suffix in self.file_extensions, f"Unsupported file extension: {path.suffix}, {self.file_extensions}"
        if path.suffix == '.json':
            self.save_json(self.data, path)
        elif path.suffix == '.yaml':
            self.save_yaml(self.data, path, default_flow_style=False)
        else:
            raise NotImplementedError(path.suffix)

    @staticmethod
    def load_yaml(path: Path,) -> dict:
        assert YAML_SUPPORT, YAML_NOT_DETECTED_MESSAGE
        with open(path) as file:
            params = yaml.load(file, Loader=SafeLoader)
        return params

    @staticmethod
    def save_yaml(data: dict, path: Path, **kwargs):
        assert YAML_SUPPORT, YAML_NOT_DETECTED_MESSAGE
        with open(path, 'w') as outfile:
            yaml.dump(data, outfile, **kwargs)

    @staticmethod
    def load_json(path: Path,) -> dict:
        with open(path) as file:
            params = json.load(file)
        return params

    @staticmethod
    def save_json(data: dict, path: Path):
        with open(path, 'w') as outfile:
            json.dump(data, outfile)
