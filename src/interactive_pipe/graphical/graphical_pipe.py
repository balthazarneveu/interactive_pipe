from typing import List, Optional
from graphical.filter import Filter
from headless.pipeline import HeadlessPipeline
from core.sliders import KeyboardSlider
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import CheckButtons, Slider


class Pipeline(HeadlessPipeline):
    """Interactive image pipe. Use sliders to fine tune your parameters
    W to write full resolution image to disk
    R to reset parameters
    I to print parameters dictionary in the command line
    E to export parameters dictionary to a yaml file
    O to import parameters dictionary from a yaml file (sliders will not update)
    G to visualize the pipeline diagram (experimental)
    H show help
    """

    def __init__(self, filters: List[Filter], name="pipeline", cache=False, inputs: list = None, parameters: dict = {}, winname=""):
        super().__init__(filters, name=name, cache=cache,
                         inputs=inputs, parameters=parameters)
        self.winname = winname
        try:
            __IPYTHON__  # noqa: F821
            self.jupyter = True
        except Exception:
            self.jupyter = False
        self.numfigs = len(self.filters[-1].outputs)
        self.slidersplot = None
        self.cursor_flag = False
        self.check_button_redraw = False
        self.slider_key = []
        

    def press(self, event):
        """Define keyboard shortcuts
        """
        for para, idx, ke_event in self.slider_key:
            incr = None
            if ke_event.keyup is not None or ke_event.modulo:
                if ke_event.keyup is not None and event.key == ke_event.keyup:
                    incr = 1
                elif event.key == ke_event.keydown:
                    incr = -1
                if incr is not None:
                    para.slider_values[idx] += incr * (para.vrange[idx][1] -
                                                       para.vrange[idx][0] + 1) * ke_event.increment
                    if ke_event.modulo:
                        para.slider_values[idx] = para.vrange[idx][0] + (para.slider_values[idx] - para.vrange[idx][0]) % (
                            para.vrange[idx][1] - para.vrange[idx][0] + 1)
                    para.slider_values[idx] = min(
                        max(para.slider_values[idx], para.vrange[idx][0]), para.vrange[idx][1])  # clip

            else:
                if event.key == ke_event.keydown:
                    para.slider_values[idx] = not para.slider_values[idx]
                    incr = 1
            if incr is not None:
                self.check_button_redraw = True
                self.update()

        self.custom_event(event.key)
        if event.key == 'r':
            self.resetsliders(forcereset=True, addslider=False)
        elif event.key == 's' or event.key == 'w':
            self.save()
        elif event.key == 'o':
            self.import_tuning()
        elif event.key == 'e':
            self.export_tuning()
        elif event.key == 'h':
            print(self.__doc__)
            if self.cursor_flag:
                print(
                    "Cursors allow you to click on the image https://mplcursors.readthedocs.io/en/stable/#default-ui")
                print("SHIFT+arrows : to move the cursor accurately")
                print("V : to show / hide")
            for para, idx, ke_event in self.slider_key:
                if ke_event.keyup is not None:
                    print(
                        f"{ke_event.keydown} / {ke_event.keyup} : {para.sliderslist[idx]} in {para.name}")
                else:
                    print(f"{ke_event.keydown} : Toggle {para.sliderslist[idx]} in {para.name}." +
                          f"Status: {para.slider_values[idx]}")

        elif event.key == 'i':
            print(self.__repr__())
        elif event.key == 'g':
            self.graph()
        elif event.key == 'q':
            plt.close(self.fig)

    def onupdate(self, val):
        u = 0
        self.check_button_redraw = False
        for pa in self.filters:
            for idx, pa_name in enumerate(pa.sliderslist):
                if isinstance(pa_name, KeyboardSlider):
                    pass
                if self.slidersplot[u] is None:
                    pass
                elif not isinstance(pa.slider_values[idx], bool):
                    pa.slider_values[idx] = self.slidersplot[u].val
                    self.check_button_redraw = True
                else:
                    pa.slider_values[idx] = self.slidersplot[u].get_status()[0]
                pa.values[list(pa.values.keys())[idx]] = pa.slider_values[idx]
                u += 1
        self.update()

    def update(self):
        if self.cursor_flag:
            if len(self.cursor.selections) > 0:
                self.cursor.remove_selection(self.cursor.selections[0])
            for slider in self.filters:
                if slider.cursor_cbk is not None:
                    try:
                        self.cursor.disconnect("add", slider.cursor_cbk)
                    except Exception:
                        pass

        resultlist = self.engine.run(self.filters, self.inputs)
        for idx in range(self.numfigs):
            result = resultlist[idx]
            self.implot[idx].set_data(
                (result * 255.).clip(0, 255).astype(np.uint8))
            # if isinstance(result, Signal):
            #     if result is not None:  # result can be None in case you only want to plot input signals
            #         if isinstance(result.y, list):
            #             linidx = 0
            #             for idz in range(len(result.y)):
            #                 self.implot[idx][idz].set_xdata(result.x[idz])
            #                 self.implot[idx][idz].set_ydata(result.y[idz])
            #                 for k, v in result.mpl_args.items():
            #                     getattr(self.implot[idx][idz], 'set_' + k)(v[idz])
            #                 if result.label[idz] is not None:
            #                     self.legend[idx].get_texts()[linidx].set_text(result.label[idz])
            #                     linidx += 1
            #         else:
            #             self.implot[idx].set_xdata(result.x)
            #             self.implot[idx].set_ydata(result.y)
            #             if result.label is not None:
            #                 self.legend[idx].get_texts()[0].set_text(result.label)

            #         self.axs[idx].set_xlim(result.xlim)
            #         self.axs[idx].set_ylim(result.ylim)
            # elif isinstance(result, Image):
            #     self.implot[idx].set_data(result.img if not result.colored else (result.img *
            #                                                                      255.).clip(0, 255).astype(np.uint8))
            #     self.implot[idx].set(clim=(result.vmin, result.vmax))
            #     if result.title is not None:
            #         self.axs[idx].set_title(result.title, fontsize=result.font_size)
            # elif isinstance(result, np.ndarray):
            #     self.implot[idx].set_data((result * 255.).clip(0, 255).astype(np.uint8))
        if not self.jupyter and self.check_button_redraw:
            plt.draw()  # only needed for check buttons when figures gets stale

    def resetsliders(self, forcereset=False, addslider=True):
        """Create sliders at their initial slider_values
        """
        def nothing(x):
            pass
        u = 0
        u_slid = 0
        if addslider:
            self.axes, self.slidersplot = [], []
        if self.jupyter:
            return
        total_sliders = np.array([len(pa.sliderslist)
                                 for pa in self.filters]).sum()
        total_buttons = np.array([len([sl for sl in pa.defaultvalue if isinstance(sl, bool)])
                                  for pa in self.filters]).sum()
        total_kb = np.array(
            [len([sl for sl in pa.slidertype if isinstance(sl, KeyboardSlider)]) for pa in self.filters]).sum()
        total_sliders = total_sliders - total_buttons - total_kb
        slider_shrink_factor = np.clip(5. / max(total_sliders, 1), 0., 1.)
        button_shrink_factor = np.clip(5. / max(total_buttons, 1), 0., 1.)
        alternate_buttons = 0
        for pa in self.filters:
            for idx, pa_name in enumerate(pa.sliderslist):
                if forcereset:
                    dfval = pa.defaultvalue[idx]
                else:
                    dfval = pa.slider_values[idx]
                if addslider:
                    defaultval = dfval
                    axcolor = 'lightgoldenrodyellow'
                    if isinstance(pa.slidertype[idx], KeyboardSlider):
                        self.axes.append(None)
                        self.slider_key.append((pa, idx, pa.slidertype[idx]))
                        self.slidersplot.append(None)
                    elif isinstance(defaultval, bool):
                        x_offset_button = 0.01
                        self.axes.append(
                            plt.axes([
                                x_offset_button,
                                0.1 + alternate_buttons * 0.04 * button_shrink_factor,
                                0.08,  # button width
                                # button height
                                max(0.04 * button_shrink_factor, 0.02)
                            ]))
                        alternate_buttons += 1
                        self.slidersplot.append(
                            CheckButtons(
                                self.axes[u],
                                [
                                    pa_name.replace(" ", "_"),
                                ],
                                actives=[defaultval],
                            ))
                    else:
                        if abs(pa.vrange[idx][1] - pa.vrange[idx][0]) > 0:
                            self.axes.append(
                                plt.axes([
                                    0.25, 0.1 + u_slid * 0.04 * slider_shrink_factor, 0.65, 0.03 * slider_shrink_factor
                                ],
                                    facecolor=axcolor))
                            self.slidersplot.append(
                                Slider(self.axes[u],
                                       pa_name.replace(" ", "_"),
                                       pa.vrange[idx][0],
                                       pa.vrange[idx][1],
                                       valinit=defaultval,
                                       valstep=(pa.vrange[idx][1] - pa.vrange[idx][0]) / 1000.))
                            u_slid += 1
                        else:
                            self.slidersplot.append(None)
                            continue
                    u += 1
                else:
                    if self.slidersplot is not None:
                        if self.slidersplot[u] is None:
                            pa.slider_values[idx] = pa.defaultvalue[idx]

                            pass
                        elif not isinstance(pa.slider_values[idx], bool):
                            self.slidersplot[u].reset()
                        else:
                            pa.slider_values[idx] = dfval
                            if self.slidersplot[u].get_status()[0] != dfval:
                                self.slidersplot[u].set_active(0)
                        u += 1
        if forcereset:
            self.update()
            
    def custom_event(self, keyboard):
        """Custom event defined for each filter
        """
        update_needed = False
        kb = keyboard.replace(" ", "space")
        kb = kb.replace("+", "plus")
        kb = kb.replace("-", "minus")

        for prc in self.filters:
            cust_event = getattr(prc, f"custom_event_{kb}", None)
            if callable(cust_event):
                cust_event()
                update_needed = True
        if update_needed:
            self.check_button_redraw = True
            self.update()

    def __gui(self, figsize=None):
        """Create pyplot GUI
        to interactively visualize the imagePipe when changing tuning sliders for each processBlock
        """
        self.parameters["gui"] = True
        self.fig, self.axs = plt.subplots(ncols=self.numfigs, figsize=figsize)
        if not self.jupyter:
            self.fig.canvas.manager.set_window_title(self.winname)
        if self.numfigs == 1:
            self.axs = [self.axs]
        totalsliders = int(np.array([len(pa.sliderslist)
                           for pa in self.filters]).sum())
        # RESIZE ONLY TO ADD SLIDERS IF NECESSARY : USEFUL FOR INPUT PLOTS WITHOUT INTERACTIVE SLIDERS
        if not self.jupyter and totalsliders > 0:
            plt.subplots_adjust(left=0.1, bottom=0.4)
        self.resetsliders(addslider=False)
        resultlist = self.engine.run(self.filters, self.inputs)
        self.implot = [None for _ in range(len(self.axs))]
        self.legend = [None for _ in range(len(self.axs))]
        for idx in range(self.numfigs):
            result = resultlist[idx]
            # if isinstance(result, Signal):
            #     self.implot[idx] = []
            #     self.legend[idx] = result.plot(ax=self.axs[idx], implot=self.implot[idx])
            # else:
            #     if not isinstance(result, Signal):
            #         if isinstance(result, Image):
            #             self.implot[idx] = self.axs[idx].imshow(result.img,
            #                                                     vmin=result.vmin,
            #                                                     vmax=result.vmax,
            #                                                     cmap=result.cmap,
            #                                                     norm=result.norm)
            #         elif isinstance(result, np.ndarray):
            #             self.implot[idx] = self.axs[idx].imshow((result * 255.).clip(0, 255).astype(np.uint8))
            #     for ax in self.axs:
            #         ax.margins(x=0)
            self.implot[idx] = self.axs[idx].imshow(
                (result * 255.).clip(0, 255).astype(np.uint8))
            for ax in self.axs:
                ax.margins(x=0)
        if self.cursor_flag:
            import mplcursors
            cursor = mplcursors.cursor()
            self.cursor = cursor
            for slider in self.filters:
                slider.set_cursor(self.cursor)
        self.resetsliders(addslider=True, forcereset=False)
        self.update()
        for slid in self.slidersplot:
            if slid is None:
                pass  # skip keyboard slider
            elif isinstance(slid, Slider):
                slid.on_changed(self.onupdate)
            else:
                slid.on_clicked(self.onupdate)
        if not self.jupyter:
            self.fig.canvas.mpl_disconnect(
                self.fig.canvas.manager.key_press_handler_id)
            self.fig.canvas.mpl_connect('key_press_event', self.press)
            plt.show()

    def gui(self, figsize=None):
        if figsize is None and self.jupyter:
            figsize = (15, 10)
        self.__gui(figsize=figsize)
        if self.jupyter:
            from ipywidgets import interact
            sliders_dict = self.__get_interact_sliders()
            interact(self.__interact_fn, **sliders_dict)

    def __get_interact_sliders(self):
        from ipywidgets import Dropdown, FloatSlider, IntSlider
        sliders = {}
        for idx, pa in enumerate(self.filters):
            for idy, paname in enumerate(pa.sliderslist):
                if isinstance(pa.vrange[idy][0], bool):
                    sliders[paname] = Dropdown(options=[0, 1] if not pa.defaultvalue[idy] else [1, 0],
                                               description=paname)
                elif isinstance(pa.vrange[idy][0], int):
                    sliders[paname] = IntSlider(min=pa.vrange[idy][0],
                                                max=pa.vrange[idy][1],
                                                value=pa.defaultvalue[idy])
                else:
                    sliders[paname] = FloatSlider(min=pa.vrange[idy][0],
                                                  max=pa.vrange[idy][1],
                                                  step=0.01,
                                                  value=pa.defaultvalue[idy])
        return sliders

    def __interact_fn(self, **kwargs):
        from IPython.display import display
        for idx, pa in enumerate(self.filters):
            for idy, paname in enumerate(pa.sliderslist):
                self.filters[idx].slider_values[idy] = kwargs[paname]
        self.update()
        self.fig.canvas.draw()
        display(self.fig)
