import logging
from pathlib import Path
from typing import Optional, Callable

import yaml
from core import PipelineCore
from yaml.loader import SafeLoader


class HeadlessPipeline(PipelineCore):
    """Adds some useful I/O to the pipeline core such as
    - importing/exporting tuning
    - printing current parameters in the terminal
    """
    @staticmethod
    def check_path(path: Optional[Path] = None) -> Path:
        # @TODO: pop up to ask a file path (opens a selection file dialog if path is None)
        assert path is not None
        assert isinstance(path, Path)
        return path

    @staticmethod
    def safe_path_with_suffix(path: Path) -> Path:
        # Protect against overwritting an existing file
        idx = 1
        orig_path = path
        while path.is_file():
            path = orig_path.with_name('%s_%d%s' % (
                orig_path.stem, idx, orig_path.suffix))
            idx += 1
        return path

    def export_tuning(self, path: Optional[Path] = None) -> None:
        """Export yaml tuning to disk 
        """
        path = self.check_path(path)

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

        with open(self.safe_path_with_suffix(path), 'w') as outfile:
            yaml.dump(saved_dict, outfile, default_flow_style=False)

    def import_tuning(self, path: Path = None) -> None:
        """Open a yaml tuning and apply to GUI
        """
        path = self.check_path(path)
        assert path.exists()
        with open(path) as yaml_file:
            forced_params = yaml.load(yaml_file, Loader=SafeLoader)
        self.set_parameters(forced_params)
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
            ret += "\"%s\"" % sl.name + \
                ":[" + ",".join(map(lambda x: "%f" % x, sl.values)) + "],\n"
        ret = ret[:-2] + "\n"  # remove comma for yaml
        ret += "}"
        return ret

    def save(self, path: Path = None, data_wrapper_fn: Callable = None) -> Path:
        """Save full resolution image
        """
        path = self.check_path(path)
        result_full = self.run()
        if not isinstance(path, Path):
            path = Path(path)
        self.export_tuning(path.with_suffix(".yaml"))
        if not isinstance(result_full, list):
            result_full = [result_full]
        for num, res_current in enumerate(result_full):
            current_name = path.with_name(
                path.stem + "_" + str(num) + path.suffix)
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
