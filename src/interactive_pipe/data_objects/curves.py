import numpy as np
from pathlib import Path
from typing import Any, Optional, Union, List, Tuple
import logging

from interactive_pipe.data_objects.data import Data

SIGNAL_BACKEND_MPL = "matplotlib"
SIGNAL_BACKEND_PD = "pandas"
SIGNAL_BACKEND_PICKLE = "pickle"
SIGNAL_BACKENDS = [SIGNAL_BACKEND_PICKLE, SIGNAL_BACKEND_PD, SIGNAL_BACKEND_MPL]


signal_backends = [SIGNAL_BACKEND_PICKLE]  # automatically available

try:
    import matplotlib.pyplot as plt
    signal_backends.append(SIGNAL_BACKEND_MPL)
except:
    logging.info("matplotlib is not available")

try:
    import pandas as pd
    signal_backends.append(SIGNAL_BACKEND_PD)
except:
    logging.info("pandas is not available")


class SingleCurve(Data):
    """SingleCurve are 2D signals you can plot, defined by x and y numpy arrays
    
    You'd normally use matplotlib.plot(x, y, label)
    - .from_file("data.csv") containing x,y columns
    - save as:
        - .csv (not style, label or markers exported)
        - .pkl (dict)
    """
    def __init__(self,
                x:Optional[Union[list[np.ndarray], np.ndarray]] =None,
                y: Union[list[np.ndarray], np.ndarray]=None,
                style: Optional[str]=None,
                linewidth:Optional[int]=None,
                markersize: Optional[int]=None,
                alpha: Optional[float]=None,
                label: Optional[str]=None
    ):
        if x is not None and y is not None:
            assert len(x) == len(y), f"abciss {len(x)} and oordinate {len(y)} shall match"
        data = {
            "x": x,
            "y": y,
            "label": label,
            "style": style,
            "linewidth": linewidth,
            "markersize": markersize,
            "alpha": alpha
        }
        super().__init__(data)

    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg", ".csv", ".pkl"]

    def _save(
            self,
            path: Path,
            backend=None,
            figsize=None,
            xlabel:Optional[str]=None,
            ylabel: Optional[str]=None,
            title: Optional[str]=None,
            grid: Optional[bool]= None
        ):
        assert path is not None, "Save requires a path"
        self.path = path
        crv = Curve([self], xlabel=xlabel, ylabel=ylabel, title=title, grid=grid)
        if path.suffix == ".csv":
            SingleCurve.save_tabular(self.data, path)
        elif path.suffix == ".pkl":
            Data.save_binary(self.data, path)
        elif path.suffix in [".png", "jpg"]:
            crv.save_figure(path=path, backend=backend, figsize=figsize)


    def _load(
            self, 
            path: Path, 
            style: Optional[str]=None,
            label: Optional[str]=None,
            linewidth:Optional[int]=None,
            markersize: Optional[int]=None,
            alpha: Optional[float]=None,
        ) -> dict:
        assert path.suffix in [".csv", ".pkl"]
        self.path = path
        if path.suffix == ".csv":
            df = pd.read_csv(self.path)
            data = {
                "x": df["x"],
                "y": df["y"],
                "label": label,
                "style": style,
                "linewidth": linewidth,
                "markersize": markersize,
                "alpha": alpha
            }
        elif path.suffix == ".pkl":
            data = Data.load_binary(path)
            if style is not None:
                data["style"] = style
            if label is not None:
                data["label"] = label
            if linewidth is not None:
                data["linewidth"] = linewidth
            if markersize is not None:
                data["markersize"] = markersize
            if alpha is not None:
                data["alpha"] = alpha
        return data
    

    def show(self, figsize=None, 
            xlabel:Optional[str]=None,
            ylabel: Optional[str]=None,
            title: Optional[str]=None,
            grid: Optional[bool]= None
        ):
        crv = Curve([self], xlabel=xlabel, ylabel=ylabel, title=title, grid=grid)
        crv.show(figsize=figsize)
    
    def as_dataframe(self):#-> pd.DataFrame
        df = SingleCurve.dataframe_from_data(self.data)
        self.df = df
        return df

    @staticmethod
    def dataframe_from_data(data): #-> pd.DataFrame
        assert SIGNAL_BACKEND_PD in signal_backends
        df = pd.DataFrame.from_dict(dict(x=data["x"], y=data["y"]))
        return df
    
    @staticmethod
    def save_tabular(data, path: Path):
        assert path.suffix == ".csv"
        df = SingleCurve.dataframe_from_data(data)
        df.to_csv(path, index=False)

class Curve(Data):
    def __init__(self, 
                 curves: List[SingleCurve],
                 xlabel:Optional[str]=None,
                 ylabel: Optional[str]=None,
                 title: Optional[str]=None,
                 grid: Optional[bool]= None,
                 xlim: Optional[Tuple[int, int]]= None,
                 ylim: Optional[Tuple[int, int]]= None) -> None:
        if curves is None:
            curve_list = []
        elif isinstance(curves, SingleCurve):
            curve_list = [curves]
            logging.debug("Empty curve")
        elif isinstance(curves, np.ndarray):
            curve_list = [SingleCurve(y=curves)]
            logging.debug("Empty curve")
        elif isinstance(curves, dict):
            curve_list = [SingleCurve(**curves)]
            logging.debug("Empty curve")
        elif isinstance(curves, list) or isinstance(curves, tuple):
            if all(isinstance(item, SingleCurve) for item in curves):
                curve_list = curves
            else:
                curve_list = []
                for curve in curves:
                    current_curve = self.__create_curve_from_abbreviation(curve)
                    curve_list.append(current_curve)
        data = {
            "curves": curve_list,
            "xlabel": xlabel,
            "ylabel": ylabel,
            "title": title,
            "grid": grid,
            "xlim": xlim,
            "ylim": ylim
        }
        super().__init__(data)

    def __create_curve_from_abbreviation(self, curve: Union[list, tuple, dict, SingleCurve, np.ndarray]):
        current_curve = None
        if isinstance(curve, list) or isinstance(curve, tuple):
            assert len(curve)>=2, f"wrong amount of parameters, should be x,y but got \n{curve}"
            style = None
            if len(curve)>=3:
                style = curve[2]
                if style is None or isinstance(style, str):
                    label = None
                    if len(curve)>=4:
                        label = curve[3]
                        if label is not None:
                            assert isinstance(label, str)
                    current_curve = SingleCurve(x=curve[0], y=curve[1], style=style, label=label)
                elif isinstance(style, dict):
                    current_curve = SingleCurve(x=curve[0], y=curve[1], **style)
            else:
                current_curve = SingleCurve(x=curve[0], y=curve[1])
        elif isinstance(curve, dict):
            current_curve = SingleCurve(**curve)
        elif isinstance(curve, SingleCurve):
            current_curve = curve
        elif isinstance(curve, np.ndarray):
            current_curve = SingleCurve(x=None, y=curve)
        assert current_curve is not None, f"could not create a single curve from abbreviation: {curve}"
        return current_curve

    def append(self, new_curve: SingleCurve):
        self.data["curves"].append(new_curve)

    def prepend(self, new_curve: SingleCurve):
        self.data["curves"].insert(new_curve, 0)

    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg", ".pkl"]
    
    def _load(
            self, 
            path: Path
        ) -> dict:
        assert path.suffix in [".pkl"]
        self.path = path
        if path.suffix == ".pkl":
            data = Data.load_binary(path)
        return data
    def _save(self, path: Path, backend=None, figsize=None):
        assert path is not None, "Save requires a path"
        self.path = path
        if path.suffix == ".pkl":
            Data.save_binary(self.data, path)
        elif path.suffix in [".png", ".jpg"]:
            self.save_figure(self.data, self.path, backend=backend, figsize=figsize)
    
    @staticmethod
    def save_figure(data, path: Path, backend=None, figsize=None):
        if backend is None:
            backend = SIGNAL_BACKEND_MPL
        assert backend in [SIGNAL_BACKEND_MPL]
        if backend == SIGNAL_BACKEND_MPL:
            Curve.save_figure_mpl(data, path, figsize=figsize)
    
    @staticmethod
    def save_figure_mpl(data, path: Path, figsize=None):
        fig, ax = plt.subplots(figsize=figsize)
        Curve._plot_curve(data, ax=ax)
        plt.savefig(path)

    def create_plot(self, ax=None):
        plt_obj = Curve._plot_curve(self.data, ax=ax)
        return plt_obj

    def update_plot(self, plt_obj, ax=None):
        Curve._update_plot(self.data, plt_obj, ax=ax)
    
    @staticmethod
    def _update_plot(data, plt_obj, ax=None):
        texts = ax.get_legend().get_texts()
        linear_index = 0
        for curve_idx, curve in enumerate(data["curves"]):
            if curve.data.get("x", None) is not None:
                plt_obj[curve_idx][0].set_xdata(curve.data["x"])
            if curve.data.get("y", None) is not None:
                plt_obj[curve_idx][0].set_ydata(curve.data["y"])
            # plt_obj.get_texts().set_text(curve.data["label"][curve_idx])
            if curve.data["label"] is not None:
                texts[linear_index].set_text(curve.data["label"])
                linear_index+=1
            
        if ax is not None:
            if data.get("title", None) is not None:
                ax.set_title(data["title"])
            if data.get("xlabel", None) is not None:
                ax.set_xlabel(data["xlabel"])
            if data.get("ylabel", None) is not None:
                ax.set_ylabel(data["ylabel"])
            if data.get("grid", None) is not None:
                ax.grid(data["grid"])
            if data.get("xlim", None) is not None:
                ax.set_xlim(data["xlim"])
            if data.get("ylim", None) is not None:
                ax.set_ylim(data["ylim"])
        
        return plt_obj
    
    @staticmethod
    def _plot_curve(data, ax=None):
        legend_flag = False
        plt_obj = []
        for curve in data["curves"]:
            if curve.data.get("x", None) is not None:
                inps = [curve.data["x"], curve.data["y"],]
            else:
                inps = [curve.data["y"],]
            if curve.data.get("style", None) is not None:
                inps.append(curve.data["style"])
            if curve.data.get("label", None) is not None:
                legend_flag=True
            plt_obj.append(
                ax.plot(
                    *inps,
                    label=curve.data.get("label", None),
                    linewidth=curve.data.get("linewidth", None),
                    markersize=curve.data.get("markersize", None),
                    alpha=curve.data.get("alpha", None)
                )
            )
        if legend_flag:
            ax.legend(loc='upper right')
        if data.get("title", None) is not None:
            ax.set_title(data["title"])
        if data.get("xlabel", None) is not None:
            ax.set_xlabel(data["xlabel"])
        if data.get("ylabel", None) is not None:
            ax.set_ylabel(data["ylabel"])
        if data.get("grid", None) is not None:
            ax.grid(data["grid"])
        if data.get("xlim", None) is not None:
            ax.set_xlim(data["xlim"])
        if data.get("ylim", None) is not None:
            ax.set_ylim(data["ylim"])
        return plt_obj
    def show(self, figsize=None):
        fig, ax = plt.subplots(figsize=figsize)
        Curve._plot_curve(self.data, ax=ax)
        plt.show()
