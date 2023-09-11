import numpy as np
from pathlib import Path
from typing import Any, Optional, Union
import logging

from interactive_pipe.data_objects.data import Data

signal_backends = []

SIGNAL_BACKEND_MPL = "matplotlib"
SIGNAL_BACKENDS = [SIGNAL_BACKEND_MPL,]

try:
    import matplotlib.pyplot as plt
    signal_backends.append(SIGNAL_BACKEND_MPL)
except:
    logging.info("matplotlib is not available")


class Curve(Data):
    def __init__(self, 
                 x:Optional[Union[list[np.ndarray], np.ndarray]] =None,
                 y: Union[list[np.ndarray], np.ndarray]=None,
                 linewidth:Optional[int]=None,
                 markersize: Optional[int]=None,
                 alpha: Optional[float]=None,
                 label: Optional[str]=None,
                 style: Optional[str]=None,
                 xlabel:Optional[str]=None, ylabel: Optional[str]=None, title: Optional[str]=None, grid: Optional[bool]= None) -> None:
        data = {
            "x": x,
            "y": y,
            "label": label,
            "style": style,
            "linewidth": linewidth,
            "markersize": markersize,
            "alpha": alpha,
            "xlabel": xlabel,
            "ylabel": ylabel,
            "title": title,
            "grid": grid
        }
        super().__init__(data)
    
    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg"]
    
    def _save(self, path: Path, backend=None, figsize=None):
        assert path is not None, "Save requires a path"
        self.path = path
        self.save_figure(self.data, self.path, backend=backend, figsize=figsize)
    
    @staticmethod
    def save_figure(data, path: Path, backend=None, figsize=None):
        if backend is None:
            backend = SIGNAL_BACKEND_MPL
        assert backend in SIGNAL_BACKENDS
        if backend == SIGNAL_BACKEND_MPL:
            Curve.save_figure_mpl(data, path, figsize=figsize)
    
    @staticmethod
    def save_figure_mpl(data, path: Path, figsize=None):
        Curve._plot_curve(data, figsize=figsize)
        plt.savefig(path)


    @staticmethod
    def _plot_curve(data, figsize=None):
        fig = plt.figure(figsize=figsize)
        if data.get("x", None) is not None:
            inps = [data["x"], data["y"],]
        else:
            inps = [data["y"],]
        if data.get("style", None) is not None:
            inps.append(data["style"])
        plt.plot(
            *inps,
            linewidth=data.get("linewidth", None),
            alpha=data.get("alpha", None)
        )
        if data.get("title", None) is not None:
            plt.title(data["title"])
        if data.get("xlabel", None) is not None:
            plt.xlabel(data["xlabel"])
        if data.get("ylabel", None) is not None:
            plt.ylabel(data["ylabel"])
        if data.get("grid", None) is not None:
            plt.grid(data["grid"])

    def show(self, figsize=None):
        Curve._plot_curve(self.data, figsize=figsize)
        plt.show()



if __name__ == '__main__':
    absciss = np.linspace(-1., 1.5, 25)
    sig = Curve(
        absciss,
        np.cos(17.*absciss),
        style="r--",
        alpha=0.2,
        title="totot",
        xlabel="absciss",
        ylabel="oordinate",
        grid=True
    )
    sig.show()
    # sig.save(figsize=(18, 2))