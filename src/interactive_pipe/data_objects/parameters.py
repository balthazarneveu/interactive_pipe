from pathlib import Path
import yaml
import json
from yaml.loader import SafeLoader
from interactive_pipe.data_objects.data import Data

class Parameters(Data):
    def _set_file_extensions(self):
        self.file_extensions = ['.yaml', '.json']
    def _load(self, path: Path):
        with open(path) as file:
            if path.suffix == '.yaml':
                params = yaml.load(file, Loader=SafeLoader)
            elif path.suffix == '.json':
                params = json.load(file)
            else:
                raise ValueError(f"Unsupported file extension: {path.suffix}")
        return params
    def _save(self, path:Path):
        with open(path, 'w') as outfile:
            if path.suffix == '.yaml':
                yaml.dump(self.data, outfile, default_flow_style=False)
            elif path.suffix == '.json':
                json.dump(self.data, outfile)
            else:
                raise ValueError(f"Unsupported file extension: {path.suffix}")