import numpy as np
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
import logging

from interactive_pipe.data_objects.data import Data


class Table(Data):
    """Tabular data for display in interactive_pipe.
    
    Works without pandas. Pandas features (DataFrame input, csv export)
    available when pandas is installed.
    
    Attributes:
        .columns - list of column names
        .values - 2D list of values (row-major)
        .title - optional title
        .precision - float formatting precision
    """

    def __init__(
        self,
        data: Union[Dict[str, List], List[Dict], np.ndarray, None] = None,
        columns: Optional[List[str]] = None,
        title: Optional[str] = None,
        precision: int = 2,
    ):
        if data is None:
            # Allow creation from Path (handled by parent class)
            data_dict = {"columns": [], "values": []}
        elif isinstance(data, Path):
            # Handled by parent class
            super().__init__(data, columns=columns, title=title, precision=precision)
            return
        else:
            data_dict = self._normalize_data(data, columns)
        
        internal_data = {
            "columns": data_dict["columns"],
            "values": data_dict["values"],
            "title": title,
            "precision": precision,
        }
        super().__init__(internal_data)

    def _normalize_data(
        self, data: Union[Dict[str, List], List[Dict], np.ndarray], columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Convert various input formats to internal format."""
        if isinstance(data, dict):
            # Dict of lists: {"col1": [1,2,3], "col2": [4,5,6]}
            if not all(isinstance(v, list) for v in data.values()):
                raise TypeError("Dict input must have list values")
            col_names = list(data.keys())
            if not col_names:
                return {"columns": [], "values": []}
            # Check all lists have same length
            lengths = [len(v) for v in data.values()]
            if len(set(lengths)) > 1:
                raise ValueError(
                    f"All columns must have the same length. Got lengths: {lengths}"
                )
            # Convert to row-major format
            num_rows = lengths[0]
            values = [[data[col][row] for col in col_names] for row in range(num_rows)]
            return {"columns": col_names, "values": values}
        
        elif isinstance(data, list):
            if not data:
                return {"columns": [], "values": []}
            # List of dicts: [{"col1": 1, "col2": 4}, {"col1": 2, "col2": 5}]
            if isinstance(data[0], dict):
                col_names = list(data[0].keys())
                # Check all dicts have same keys
                for i, row_dict in enumerate(data):
                    if set(row_dict.keys()) != set(col_names):
                        raise ValueError(
                            f"Row {i} has different keys. Expected {col_names}, got {list(row_dict.keys())}"
                        )
                values = [[row_dict[col] for col in col_names] for row_dict in data]
                return {"columns": col_names, "values": values}
            else:
                raise TypeError(
                    "List input must be a list of dictionaries. "
                    "For 2D arrays, use numpy array with columns parameter."
                )
        
        elif isinstance(data, np.ndarray):
            # 2D numpy array with columns parameter
            if len(data.shape) != 2:
                raise ValueError(
                    f"Numpy array must be 2D, got shape {data.shape}"
                )
            if columns is None:
                raise ValueError(
                    "columns parameter is required when using numpy array input"
                )
            if len(columns) != data.shape[1]:
                raise ValueError(
                    f"Number of columns ({len(columns)}) must match array width ({data.shape[1]})"
                )
            values = data.tolist()
            return {"columns": columns, "values": values}
        
        else:
            raise TypeError(
                f"Unsupported data type: {type(data)}. "
                "Supported: dict of lists, list of dicts, 2D numpy array"
            )

    @property
    def columns(self) -> List[str]:
        return self.data["columns"]

    @columns.setter
    def columns(self, columns: List[str]):
        if not isinstance(columns, list):
            raise TypeError(f"columns must be a list, got {type(columns)}")
        if not all(isinstance(c, str) for c in columns):
            raise TypeError("All column names must be strings")
        self.data["columns"] = columns

    @property
    def values(self) -> List[List]:
        return self.data["values"]

    @values.setter
    def values(self, values: List[List]):
        if not isinstance(values, list):
            raise TypeError(f"values must be a list, got {type(values)}")
        self.data["values"] = values

    @property
    def title(self) -> Optional[str]:
        return self.data["title"]

    @title.setter
    def title(self, title: Optional[str]):
        if title is not None and not isinstance(title, str):
            raise TypeError(f"title must be a string or None, got {type(title)}")
        self.data["title"] = title

    @property
    def precision(self) -> int:
        return self.data["precision"]

    @precision.setter
    def precision(self, precision: int):
        if not isinstance(precision, int):
            raise TypeError(f"precision must be an integer, got {type(precision)}")
        if precision < 0:
            raise ValueError(f"precision must be non-negative, got {precision}")
        self.data["precision"] = precision

    def __getitem__(self, key: Union[int, str, slice]):
        """Access data by row index, column name, or slice."""
        if isinstance(key, int):
            # Return row
            if key >= len(self.values):
                raise IndexError(
                    f"Row index {key} out of range (max: {len(self.values) - 1})"
                )
            return dict(zip(self.columns, self.values[key]))
        elif isinstance(key, str):
            # Return column
            if key not in self.columns:
                raise KeyError(f"Column '{key}' not found. Available: {self.columns}")
            col_idx = self.columns.index(key)
            return [row[col_idx] for row in self.values]
        elif isinstance(key, slice):
            # Return slice of rows
            rows = self.values[key]
            return [dict(zip(self.columns, row)) for row in rows]
        else:
            raise TypeError(f"Key must be int, str, or slice, got {type(key)}")

    def _set_file_extensions(self):
        self.file_extensions = [".csv", ".pkl"]

    def _save(self, path: Path, **kwargs):
        if path.suffix == ".pkl":
            Data.save_binary(self.data, path)
        elif path.suffix == ".csv":
            # CSV requires pandas - will be handled in Commit 2
            raise RuntimeError(
                "CSV export requires pandas. Install with: pip install pandas"
            )
        else:
            raise ValueError(
                f"Unsupported file extension: {path.suffix}. Supported: .pkl, .csv"
            )

    def _load(self, path: Path, **kwargs) -> Dict[str, Any]:
        if path.suffix == ".pkl":
            data = Data.load_binary(path)
            return data
        elif path.suffix == ".csv":
            # CSV requires pandas - will be handled in Commit 2
            raise RuntimeError(
                "CSV import requires pandas. Install with: pip install pandas"
            )
        else:
            raise ValueError(
                f"Unsupported file extension: {path.suffix}. Supported: .pkl, .csv"
            )
