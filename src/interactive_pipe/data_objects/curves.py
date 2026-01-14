import numpy as np
from pathlib import Path
from typing import Optional, Union, List, Tuple
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
except ImportError:
    logging.info("matplotlib is not available")

try:
    import pandas as pd

    signal_backends.append(SIGNAL_BACKEND_PD)
except ImportError:
    message = "pandas is not available."
    message += (
        "\nto install see: https://pandas.pydata.org/docs/getting_started/install.html"
    )
    message += "\npip install pandas"
    message += "\nyou won't be able to export curves as .csv spreadsheets"
    logging.warning(message)


class SingleCurve(Data):
    """SingleCurve are 2D signals you can plot, defined by x and y numpy arrays
    Attributes:
        .x
        .y
        .label
        .alpha
        .style
    You'd normally use matplotlib.plot(x, y, label)
    - .from_file("data.csv") containing x,y columns
    - save as:
        - .csv (not style, label or markers exported)
        - .pkl (dict)
    """

    def __init__(
        self,
        x: Optional[Union[List[np.ndarray], np.ndarray]] = None,
        y: Union[List[np.ndarray], np.ndarray] = None,
        style: Optional[str] = None,
        label: Optional[str] = None,
        linestyle: Optional[str] = None,
        linewidth: Optional[int] = None,
        markersize: Optional[int] = None,
        alpha: Optional[float] = None,
    ):
        if x is not None and y is not None:
            if len(x) != len(y):
                raise ValueError(
                    f"x and y lengths must match: x has {len(x)} elements, y has {len(y)} elements"
                )
        data = {
            "x": x,
            "y": y,
            "label": label,
            "style": style,
            "linestyle": linestyle,
            "linewidth": linewidth,
            "markersize": markersize,
            "alpha": alpha,
        }
        super().__init__(data)

    @property
    def x(self) -> np.ndarray:
        return self.data["x"]

    @x.setter
    def x(self, x: np.ndarray):
        self.data["x"] = x

    @property
    def y(self) -> np.ndarray:
        return self.data["y"]

    @y.setter
    def y(self, y: np.ndarray):
        self.data["y"] = y

    @property
    def label(self) -> str:
        return self.data["label"]

    @label.setter
    def label(self, label):
        if label is not None and not isinstance(label, str):
            raise TypeError(f"label must be a string or None, got {type(label)}")
        self.data["label"] = label

    @property
    def style(self) -> str:
        return self.data["style"]

    @style.setter
    def style(self, style):
        if style is not None and not isinstance(style, str):
            raise TypeError(f"style must be a string or None, got {type(style)}")
        self.data["style"] = style

    @property
    def alpha(self) -> float:
        return self.data["alpha"]

    @alpha.setter
    def alpha(self, alpha):
        if alpha is None:
            self.data["alpha"] = None
        else:
            if not isinstance(alpha, (float, int)):
                raise TypeError(f"alpha must be a number, got {type(alpha)}")
            if not (0 <= alpha <= 1):
                raise ValueError(f"alpha must be between [0, 1], got {alpha}")
            self.data["alpha"] = alpha

    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg", ".csv", ".pkl"]

    def _save(
        self,
        path: Path,
        backend=None,
        figsize=None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        title: Optional[str] = None,
        grid: Optional[bool] = None,
    ):
        if path is None:
            raise ValueError("Save requires a path")
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
        style: Optional[str] = None,
        label: Optional[str] = None,
        linestyle: Optional[str] = None,
        linewidth: Optional[int] = None,
        markersize: Optional[int] = None,
        alpha: Optional[float] = None,
    ) -> dict:
        if path.suffix not in [".csv", ".pkl"]:
            raise ValueError(
                f"Unsupported file extension: {path.suffix}, expected .csv or .pkl"
            )
        self.path = path
        if path.suffix == ".csv":
            df = pd.read_csv(self.path)
            data = {
                "x": df["x"],
                "y": df["y"],
                "label": label,
                "style": style,
                "linestyle": linestyle,
                "linewidth": linewidth,
                "markersize": markersize,
                "alpha": alpha,
            }
        elif path.suffix == ".pkl":
            data = Data.load_binary(path)
            if style is not None:
                data["style"] = style
            if label is not None:
                data["label"] = label
            if linestyle is not None:
                data["linestyle"] = linestyle
            if linewidth is not None:
                data["linewidth"] = linewidth
            if markersize is not None:
                data["markersize"] = markersize
            if alpha is not None:
                data["alpha"] = alpha
        return data

    def show(
        self,
        figsize=None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        title: Optional[str] = None,
        grid: Optional[bool] = None,
    ):
        crv = Curve([self], xlabel=xlabel, ylabel=ylabel, title=title, grid=grid)
        crv.show(figsize=figsize)

    def as_dataframe(self):  # -> pd.DataFrame
        df = SingleCurve.dataframe_from_data(self.data)
        self.df = df
        return df

    @staticmethod
    def dataframe_from_data(data):  # -> pd.DataFrame
        if SIGNAL_BACKEND_PD not in signal_backends:
            raise RuntimeError(
                "pandas backend is not available. Install pandas to use this feature."
            )
        df = pd.DataFrame.from_dict(dict(x=data["x"], y=data["y"]))
        return df

    @staticmethod
    def save_tabular(data, path: Path):
        if path.suffix != ".csv":
            raise ValueError(f"save_tabular requires .csv extension, got {path.suffix}")
        df = SingleCurve.dataframe_from_data(data)
        df.to_csv(path, index=False)


class Curve(Data):
    """
    Attributes
        - `.grid`
        - `.xlabel`
        - `.ylabel`
        - `.xlim`
        - `.ylim`
        - `.title`
        - `.curves`

        It is possible to access a curve by simply using the bracket operator
        `.curves[index]` is equivalent to `[index]`

    """

    def __init__(
        self,
        curves: List[SingleCurve],
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        title: Optional[str] = None,
        grid: Optional[bool] = None,
        xlim: Optional[Tuple[int, int]] = None,
        ylim: Optional[Tuple[int, int]] = None,
    ) -> None:
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
            "ylim": ylim,
        }
        super().__init__(data)

    def __create_curve_from_abbreviation(
        self, curve: Union[list, tuple, dict, SingleCurve, np.ndarray]
    ):
        current_curve = None
        if isinstance(curve, list) or isinstance(curve, tuple):
            if len(curve) < 2:
                raise ValueError(
                    f"curve must have at least 2 elements (x, y), got {len(curve)} elements: {curve}"
                )
            style = None
            if len(curve) >= 3:
                style = curve[2]
                if style is None or isinstance(style, str):
                    label = None
                    if len(curve) >= 4:
                        label = curve[3]
                        if label is not None:
                            if not isinstance(label, str):
                                raise TypeError(
                                    f"label must be a string, got {type(label)}"
                                )
                    current_curve = SingleCurve(
                        x=curve[0], y=curve[1], style=style, label=label
                    )
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
        if current_curve is None:
            raise ValueError(
                f"could not create a single curve from abbreviation: {curve}"
            )
        return current_curve

    # .grid
    # ---------------------------------------

    @property
    def grid(self) -> bool:
        return self.data["grid"]

    @grid.setter
    def grid(self, grid: bool):
        self.data["grid"] = grid

    # .title
    # ---------------------------------------
    @property
    def title(self) -> str:
        return self.data["title"]

    @title.setter
    def title(self, title: str):
        self.data["title"] = title

    # .xlim / .ylim
    # ---------------------------------------
    @property
    def xlim(self) -> Tuple[int, int]:
        return self.data["xlim"]

    @xlim.setter
    def xlim(self, xlim: Tuple[int, int]):
        self.data["xlim"] = xlim

    @property
    def ylim(self) -> Tuple[int, int]:
        return self.data["ylim"]

    @ylim.setter
    def ylim(self, ylim: Tuple[int, int]):
        self.data["ylim"] = ylim

    # .xlabel / .ylabel
    # ---------------------------------------
    @property
    def xlabel(self) -> str:
        return self.data["xlabel"]

    @xlabel.setter
    def xlabel(self, xlabel: str):
        self.data["xlabel"] = xlabel

    @property
    def ylabel(self) -> str:
        return self.data["ylabel"]

    @ylabel.setter
    def ylabel(self, ylabel: str):
        self.data["ylabel"] = ylabel

    # .curves
    # ---------------------------------------
    @property
    def curves(self) -> List[SingleCurve]:
        return self.data["curves"]

    @curves.setter
    def curves(self, curves: List[SingleCurve]):
        self.data["curves"] = curves

    # brackets []
    # ---------------------------------------
    def __getitem__(self, key: int) -> SingleCurve:
        if isinstance(key, slice):
            return [
                self.data["curves"][idx]
                for idx in range(*key.indices(len(self.data["curves"])))
            ]
        if not isinstance(key, int):
            raise TypeError(f"key must be an integer, got {type(key)}")
        if key >= len(self.data["curves"]):
            raise IndexError(
                f"curve index {key} out of range (max: {len(self.data['curves']) - 1})"
            )
        return self.data["curves"][key]

    def __setitem__(self, key: int, value):
        if isinstance(key, slice):
            for lin_index, idx in enumerate(range(*key.indices(len(value)))):
                if idx >= len(self.data["curves"]):
                    raise IndexError(
                        f"curve index {idx} out of range (max: {len(self.data['curves']) - 1})"
                    )
                self.data["curves"][idx] = value[lin_index]
            return
        if not isinstance(key, int):
            raise TypeError(f"key must be an integer, got {type(key)}")
        if key >= len(self.data["curves"]):
            raise IndexError(
                f"curve index {key} out of range (max: {len(self.data['curves']) - 1})"
            )
        if not isinstance(value, SingleCurve):
            raise TypeError(f"value must be a SingleCurve instance, got {type(value)}")
        self.data["curves"][key] = value

    def append(self, new_curve: SingleCurve):
        self.data["curves"].append(new_curve)

    def prepend(self, new_curve: SingleCurve):
        self.data["curves"].insert(0, new_curve)

    def _set_file_extensions(self):
        self.file_extensions = [".png", ".jpg", ".pkl"]

    def _load(self, path: Path) -> dict:
        if path.suffix != ".pkl":
            raise ValueError(
                f"Unsupported file extension: {path.suffix}, expected .pkl"
            )
        self.path = path
        if path.suffix == ".pkl":
            data = Data.load_binary(path)
        return data

    def _save(self, path: Path, backend=None, figsize=None):
        if path is None:
            raise ValueError("Save requires a path")
        self.path = path
        if path.suffix == ".pkl":
            Data.save_binary(self.data, path)
        elif path.suffix in [".png", ".jpg"]:
            self.save_figure(self.data, self.path, backend=backend, figsize=figsize)

    @staticmethod
    def save_figure(data, path: Path, backend=None, figsize=None):
        if backend is None:
            backend = SIGNAL_BACKEND_MPL
        if backend not in [SIGNAL_BACKEND_MPL]:
            raise ValueError(f"backend must be {SIGNAL_BACKEND_MPL}, got {backend}")
        if backend == SIGNAL_BACKEND_MPL:
            Curve.save_figure_mpl(data, path, figsize=figsize)

    @staticmethod
    def save_figure_mpl(data, path: Path, figsize=None):
        fig, ax = plt.subplots(figsize=figsize)
        Curve._plot_curve(data, ax=ax)
        plt.savefig(path)
        plt.close(fig)

    def create_plot(self, ax=None):
        plt_obj = Curve._plot_curve(self.data, ax=ax)
        return plt_obj

    def update_plot(self, plt_obj, ax=None):
        Curve._update_plot(self.data, plt_obj, ax=ax)

    @staticmethod
    def _update_plot(data, plt_obj, ax=None):
        legend = ax.get_legend()
        if legend is not None:
            texts = legend.get_texts()
        linear_index = 0
        for curve_idx, curve in enumerate(data["curves"]):
            if curve.data.get("x", None) is not None:
                plt_obj[curve_idx][0].set_xdata(curve.data["x"])
            if curve.data.get("y", None) is not None:
                plt_obj[curve_idx][0].set_ydata(curve.data["y"])
            if curve.data["label"] is not None:
                texts[linear_index].set_text(curve.data["label"])
                linear_index += 1

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
                inps = [
                    curve.data["x"],
                    curve.data["y"],
                ]
            else:
                inps = [
                    curve.data["y"],
                ]
            has_style_fmt = curve.data.get("style", None) is not None
            if has_style_fmt:
                inps.append(curve.data["style"])
            if curve.data.get("label", None) is not None:
                legend_flag = True

            # Build kwargs - avoid redundant linestyle when style fmt string is provided
            # The fmt string (e.g., "r-o") already contains linestyle info, so passing
            # linestyle keyword would be redundant and trigger a warning
            plot_kwargs = {
                "label": curve.data.get("label", None),
                "alpha": curve.data.get("alpha", None),
            }
            # Only add linestyle if style fmt string is not provided (to avoid redundancy warning)
            if not has_style_fmt:
                linestyle = curve.data.get("linestyle", None)
                if linestyle is not None:
                    plot_kwargs["linestyle"] = linestyle

            linewidth = curve.data.get("linewidth", None)
            if linewidth is not None:
                plot_kwargs["linewidth"] = linewidth

            markersize = curve.data.get("markersize", None)
            if markersize is not None:
                plot_kwargs["markersize"] = markersize

            plt_obj.append(ax.plot(*inps, **plot_kwargs))
        if legend_flag:
            ax.legend(loc="upper right")
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
