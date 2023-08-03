from pathlib import Path
import yaml
from yaml.loader import SafeLoader
from data_objects.data import Data

class Parameters(Data):
    def _set_file_extensions(self):
        self.file_extensions = '.yaml'
    def _load(self, path: Path):
        with open(path) as yaml_file:
            params = yaml.load(yaml_file, Loader=SafeLoader)
        return params
    def _save(self, path:Path):
        with open(path, 'w') as outfile:
            yaml.dump(self.data, outfile, default_flow_style=False)