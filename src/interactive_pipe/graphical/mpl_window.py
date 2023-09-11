import matplotlib.pyplot as plt
from interactive_pipe.graphical.window import InteractivePipeWindow
import numpy as np
import matplotlib as mpl
from interactive_pipe.data_objects.curves import Curve


class MatplotlibWindow(InteractivePipeWindow):
    def __init__(self,  controls=[], name="", pipeline=None, size=None, style: str=None, rc_params=None):
        """
        style: dark_background, seaborn-v0_8-dark
        https://matplotlib.org/stable/gallery/style_sheets/style_sheets_reference.html

        rc_params: 
        ```
        rc_params = {
            'font.family': 'serif',
            'font.serif': 'Ubuntu',
            'font.size': 10
        }
        """
        super().__init__(self, size=size, pipeline=pipeline, name=name)
        self.controls = controls
        if style is not None:
            mpl.style.use(style)
        if rc_params is not None:
            for key, val in rc_params.items():
                plt.rcParams[key] = val

    def add_image_placeholder(self, row, col):
        nrows, ncols = np.array(self.image_canvas).shape
        ax_img = self.fig.add_subplot(nrows, ncols, row * ncols + col + 1)
        self.image_canvas[row][col] = {"ax": ax_img}
    
    def delete_image_placeholder(self, ax):
        ax["ax"].remove()
        self.need_redraw = True
    
    def update_style(self, ax: plt.Axes, style:dict ={}):
        if style is None:
            return
        title = style.get("title", None)
        if title:
            ax.set_title(title)


    
    def update_image(self, image_array, row, col):
        ax_dict = self.image_canvas[row][col]
        img = self.convert_image(image_array)
        current_style = self.get_current_style(row, col)
        data =  ax_dict.get("data", None)
        if data:
            if isinstance(img, np.ndarray):
                data.set_data(img)
            elif isinstance(img, Curve):
                img.update_plot(data, ax=ax_dict["ax"])
        else:
            if isinstance(img, np.ndarray):
                ax_dict["data"] = ax_dict["ax"].imshow(img)
            elif isinstance(img, Curve):
                ax_dict["data"] = img.create_plot(ax=ax_dict["ax"])
        if not (isinstance(img, Curve) and img.data["title"] is not None):
            self.update_style(ax_dict["ax"], style=current_style)


    def refresh(self):
        if not hasattr(self, "need_redraw"):
            self.need_redraw = False
        if self.pipeline is not None:
            out = self.pipeline.run()
            self.refresh_display(out)
        if self.need_redraw:
            plt.draw()
        self.need_redraw = False
    
    def convert_image(self, img):
        if isinstance(img, np.ndarray):
            return img.clip(0., 1.)
        else:
            return img