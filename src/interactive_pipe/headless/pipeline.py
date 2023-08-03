import logging
from pathlib import Path
from typing import Optional, Callable

import yaml
from core.pipeline import PipelineCore
from data_objects.parameters import Parameters



class HeadlessPipeline(PipelineCore):
    """Adds some useful I/O to the pipeline core such as
    - importing/exporting tuning
    - printing current parameters in the terminal
    """


    def export_tuning(self, path: Optional[Path] = None, override=False) -> None:
        """Export yaml tuning to disk 
        """
        export_dict = {}
        for sl in self.filters:
            export_dict[sl.name] = sl.values
        saved_dict = export_dict
        if self.parameters != {}:
            # Legacy yaml generation to add more elements to reproduce
            if "path" in self.parameters:
                saved_dict["path"] = self.parameters["path"]
            if "tuning" in self.parameters:
                for elt in self.parameters["tuning"]:
                    if type(self.parameters["tuning"][elt]) == dict:
                        saved_dict[elt] = {}
                        for e in self.parameters["tuning"][elt]:
                            data = self.parameters["tuning"][elt][e][0]
                            index = int(self.parameters["tuning"][elt][e][1])
                            saved_dict[elt][e] = export_dict[data][index]
                    else:
                        data = self.parameters["tuning"][elt][0]
                        index = int(self.parameters["tuning"][elt][1])
                        saved_dict[elt] = export_dict[data][index]
        Parameters(saved_dict).save(path, override=True if path is None else override)
       

    def import_tuning(self, path: Path = None) -> None:
        """Open a yaml tuning and apply to GUI
        """
        self.parameters = Parameters.load_from_file(path)
    #     self.update()
    #     self.reset_sliders(addslider=False, forcereset=False)
    #     self.redraw()

    # def reset_sliders(self, **kwargs):
    #     logging.info("Redraw sliders")

    # def update(self):
    #     logging.info("Update graphical inferface if needed")

    # def redraw(self):
    #     logging.info("Redraw graphical inferface")
    #     # self.fig.canvas.draw()

    def __repr__(self):
        """Print tuning parameters
        """
        ret = "\n{\n"
        for sl in self.filters:
            # ret += "\"%s\"" % sl.name + \
            #     ":[" + ",".join(map(lambda x: "%f" % x, sl.values)) + "],\n"
            ret += f"{sl.name} : {sl.values},\n"
        ret = ret[:-2] + "\n"  # remove comma for yaml
        ret += "}"
        return ret

    def save(self, path: Path = None, data_wrapper_fn: Callable = None, output_indexes: list = None, save_entire_buffer=False) -> Path:
        """Save full resolution image
        """
        if output_indexes is None:
            output_indexes = self.filters[-1].outputs
        if save_entire_buffer:
            output_indexes = None # you may force specific buffer index you'd like to save
        result_full = self.run()
        if not isinstance(path, Path):
            path = Path(path)
        self.export_tuning(path.with_suffix(".yaml"))
        if not isinstance(result_full, list):
            result_full = [result_full]
        for num, res_current in enumerate(result_full):
            if output_indexes is not None and not num in output_indexes:
                continue
            current_name = path.with_name(
                path.stem + "_" + str(num) + path.suffix)
            if res_current is not None and not (isinstance(res_current, list) and len(res_current) == 0):
                if data_wrapper_fn is not None:
                    data_wrapper_fn(res_current).save(current_name)
                else:
                    assert hasattr(res_current, "save")
                    res_current.save(current_name)

            # @ TODO: handle proper output suffixes namings
            logging.info("saved image %s" % current_name)
            # if isinstance(res_current, Signal):
            #     res_current.plot(out=current_name.with_suffix(".png"), ax=None, implot=None)
            #     continue
            # if isinstance(res_current, Image):
            #     img = res_current.img
            #     if res_current.cmap:
            #         plt.imshow(img, norm=res_current.norm, cmap=res_current.cmap)
            #         plt.colorbar()
            #         plt.savefig(current_name)
            #         plt.close()
            #         continue
            #     else:
            #         res_current = img
            # self.save_image(res_current.clip(0., 1.), current_name, precision=16 if "tif" in path.suffix.lower() else 8)

        return path
