import logging
import traceback
from pathlib import Path
from typing import Any, Optional, Callable
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.core.graph import get_call_graph
from interactive_pipe.core.filter import analyze_apply_fn_signature
from interactive_pipe.headless.control import Control


class HeadlessPipeline(PipelineCore):
    """PipelineCore extensions - saving/loading to disk - graphs - init from interpreted functions

    Adds some powerful features to the pipeline core such as:
    - creating a pipeline from a function as a sequential filter
    - importing/exporting parameters ("tuning") as json or yaml
    - saving output images
    - printing current parameters in the terminal
    - graph representation
    """
    @staticmethod
    def routing_indexes(inputs_names, all_variables):
        if inputs_names:
            inputs = []
            for input_index, input_name in enumerate(inputs_names):
                inputs.append(all_variables[input_name])
            if len(inputs) == 0:
                inputs = None
        else:
            inputs = None
        return inputs

    @classmethod
    def from_function(cls, pipe: Callable, inputs=None, __routing_by_indexes=False, **kwargs):
        assert isinstance(pipe, Callable)
        graph = get_call_graph(pipe)
        all_variables = {}
        total_index = 0
        function_inputs = {}
        input_routing = []
        for input_index, input_name in enumerate(graph["args"]):
            all_variables[input_name] = total_index
            function_inputs[input_name] = total_index
            if __routing_by_indexes:
                input_routing.append(total_index)
            else:
                input_routing.append(input_name)
            total_index += 1
        for filt_dict in graph["call_graph"]:
            for key in ["args", "returns"]:
                if filt_dict[key]:
                    for _, input_name in enumerate(filt_dict[key]):
                        if not input_name in all_variables.keys():
                            all_variables[input_name] = total_index
                            total_index += 1

        filters = []
        filters_count = {}
        filters_names = []
        control_list = []
        for filt_dict in graph["call_graph"]:
            # avoid duplicate filters names
            filt_name = filt_dict["function_name"]
            filter_count = filters_count.get(filt_name, -1)
            if filter_count >= 0:
                filters_count[filt_name] += 1
                filt_name = filt_name + f"_{filters_count[filt_name]}"
            else:
                filters_count[filt_name] = 0
            if __routing_by_indexes:
                inputs_filt = HeadlessPipeline.routing_indexes(
                    filt_dict["args"], all_variables)
                outputs_filt = HeadlessPipeline.routing_indexes(
                    filt_dict["returns"], all_variables)
            else:
                inputs_filt = filt_dict["args"]
                outputs_filt = filt_dict["returns"]
            logging.debug("----------------->", filt_name,
                          inputs_filt, outputs_filt)
            if isinstance(filt_dict["function_object"], FilterCore):
                filter = filt_dict["function_object"]
                filter.inputs = inputs_filt
                filter.outputs = outputs_filt
                filter.name = filt_name
                params_to_analyze = filter.controls
            else:
                # when using the @interactive decorator
                filter = FilterCore(
                    name=filt_name,
                    inputs=inputs_filt,
                    outputs=outputs_filt,
                    apply_fn=filt_dict["function_object"],
                )
                func_kwargs = analyze_apply_fn_signature(
                    filt_dict["function_object"])[1]
                params_to_analyze = {**func_kwargs, **
                                     Control.get_controls(filt_name)}
            for param_name, param_value in params_to_analyze.items():
                if isinstance(param_value, Control):
                    param_value.connect_filter(filter, param_name)
                    filter.values = {param_name: param_value.value_default}
                    control_list.append(param_value)
            filters.append(filter)
            filters_names.append(filt_name)
        logging.debug(filters_count)
        logging.debug(filters_names)
        if __routing_by_indexes:
            outputs = [all_variables[output_name]
                       for output_name in graph["returns"]]
        else:
            outputs = graph["returns"]
        if len(function_inputs) == 0 and inputs is None:
            logging.info(
                "Auto deduced that there are no arguments provided to the function")
        data_class = cls(
            filters=filters, name=graph["function_name"], inputs=input_routing, outputs=outputs, **kwargs)
        data_class.controls = control_list
        return data_class

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
        Parameters(saved_dict).save(
            path, override=True if path is None else override)

    def import_tuning(self, path: Path = None) -> None:
        """Open a json/yaml tuning file and set parameters
        """
        try:
            self.parameters = Parameters.from_file(path).data
        except Exception as exc:
            logging.warning(f"Cannot load parameters from {path}\n{exc}")
            traceback.print_exc()

    def __repr__(self):
        """Print tuning parameters
        """
        for filt in self.filters:
            print(filt)
        ret = "\n{\n"
        for sl in self.filters:
            # ret += "\"%s\"" % sl.name + \
            #     ":[" + ",".join(map(lambda x: "%f" % x, sl.values)) + "],\n"
            ret += f"{sl.name} : {sl.values},\n"
        ret = ret[:-2] + "\n"  # remove comma for yaml
        ret += "}"
        return ret

    def update_parameters_from_controls(self):
        if not hasattr(self, "controls"):
            # Not having .controls attribute
            # This happens for headless pipelines which have no list of controls
            return
        for ctrl in self.controls:
            logging.info(
                f"{ctrl.filter_to_connect.name}, {ctrl.parameter_name_to_connect}, {ctrl.value}")
            self.parameters = {ctrl.filter_to_connect.name: {
                ctrl.parameter_name_to_connect:  ctrl.value}}

    def __run(self):
        self.update_parameters_from_controls()
        result_full = super().run()
        if self.outputs is not None:
            output_indexes = self.outputs
        else:
            output_indexes = self.filters[-1].outputs
        if output_indexes:
            if isinstance(output_indexes[0], list):
                return [[None if out_index is None else result_full[out_index] for idx, out_index in enumerate(row)] for idy, row in enumerate(output_indexes)]
            return tuple(result_full[idx] for idx in output_indexes)
        else:
            return None

    def run(self):
        self.results = self.__run()
        return self.results

    def save(self, path: Path = None, data_wrapper_fn: Callable = None, output_indexes: list = None, save_entire_buffer=False) -> Path:
        """Save images
        """
        if output_indexes is None:
            if self.outputs is not None:
                output_indexes = self.outputs
            else:
                output_indexes = self.filters[-1].outputs
        if save_entire_buffer:
            output_indexes = None  # you may force specific buffer index you'd like to save
        result_full = super().run()
        if result_full is None:
            return None
        if not isinstance(path, Path):
            path = Path(path)
        self.export_tuning(path.with_suffix(".yaml"))
        assert isinstance(result_full, dict)
        for num, res_current in result_full.items():
            if output_indexes is not None and not num in output_indexes:
                continue
            current_name = path.with_name(
                path.stem + "_" + str(num) + path.suffix)
            if res_current is not None and not (isinstance(res_current, list) and len(res_current) == 0):
                try:
                    if data_wrapper_fn is not None:
                        data_wrapper_fn(res_current).save(current_name)
                    else:
                        assert hasattr(res_current, "save")
                        res_current.save(current_name)
                except Exception as exc:
                    logging.warning(f"Cannot save image {current_name}\n{exc}")
                    traceback.print_exc()
            # @ TODO: handle proper output suffixes namings
            logging.info("saved image %s" % current_name)
        return path

    def parameters_from_keyword_args(self, **kwargs) -> dict:
        new_param_dict = {}
        for key, value in kwargs.items():
            for filter_name, parameters_dict in self.parameters.items():
                parameter_names = parameters_dict.keys()
                if key in parameter_names:
                    if not filter_name in new_param_dict.keys():
                        new_param_dict[filter_name] = {}
                    new_param_dict[filter_name][key] = value
        return new_param_dict

    def __call__(self, *inputs_tuple, inputs=None, parameters={}, **kwargs) -> Any:
        if inputs is not None:
            assert isinstance(inputs, dict)
            self.inputs = inputs
            logging.info(
                f"Dict style inputs {list(inputs.keys())}, {self.inputs}")
        else:
            # @TODO: we could check that the number of inputs matches what's expected here.
            self.inputs = list(inputs_tuple)
            if self.inputs is None:
                pass
            elif len(self.inputs) == 0:
                self.inputs = None
        self.parameters = parameters
        self.parameters = self.parameters_from_keyword_args(**kwargs)
        return self.run()

    def graph_representation(self, path=None, ortho=True, view=False):
        def find_previous_key(searched_out, current_index, input_indexes, debug=False):
            last_filter_found = None
            inp_name = None
            for inp in input_indexes:
                if searched_out == inp:
                    last_filter_found = f"{inp}"
                    inp_name = f"{inp}"
            for prev_idx in range(current_index):
                filt_prev = self.filters[prev_idx]
                if filt_prev.outputs is None:
                    continue
                for inp in filt_prev.outputs:
                    if debug:
                        print(f"{searched_out}, {filt_prev.name} {inp}")
                    if searched_out == inp:
                        last_filter_found = filt_prev.name
                        inp_name = f"{inp}"
            return last_filter_found, inp_name

        def edge_label(label):
            return f"[{label}]"
        try:
            import graphviz
        except Exception as exc:
            logging.warning(
                "cannot generate pipeline graph, need to install graphviz")
            logging.warning(exc)
            return None

        dot = graphviz.Digraph(comment=self.name)
        if ortho:
            dot.attr(splines="ortho")
        assert self.inputs_routing is not None, "cannot plot the graph if input routing is not provided"
        input_indexes = self.inputs_routing
        with dot.subgraph(name='cluster_in') as inputs_graph:
            inputs_graph.attr(style="dashed", color="gray", label="Inputs")
            for inp in input_indexes:
                inputs_graph.node(
                    f"{inp}", f"🖴 {inp}",  shape="rect", color="gray", styleItem="dash")

        with dot.subgraph(name='cluster_filters') as filter_graphs:
            # filter_graphs.attr(color="transparent",)
            filter_graphs.attr(color="gray", style="dashed", label=self.name)
            for filt in self.filters:
                all_params = []
                for pa_name, pa_val in filt.values.items():
                    all_params.append(f"\n✔️ {pa_name}")
                filter_graphs.node(
                    filt.name, f"⚙️ {filt.name}" + ("".join(all_params)), shape="rect")
            for idx, filt in enumerate(self.filters):
                if filt.inputs is None:
                    continue
                for out in filt.inputs:
                    last_filter_found, inp_name = find_previous_key(
                        out, idx, input_indexes)
                    if last_filter_found is not None:
                        dot.edge(last_filter_found, filt.name,
                                 label=edge_label(inp_name))
        out_list = []
        for out_item in self.outputs:
            out_row = out_item
            if not isinstance(out_item, list) or isinstance(out_item, tuple):
                out_row = [out_item]
            for out in out_row:
                if out is None:
                    continue
                out_list.append(out)
        with dot.subgraph(name='cluster_out') as out_graph:
            out_graph.attr(style="dashed", color="gray", label="Outputs")
            for out in out_list:
                out_graph.node(f"out {out}", f"🛢️ {out}",
                               shape="rect", color="gray")
        for out in out_list:
            last_filter_found, inp_name = find_previous_key(
                out, len(self.filters), input_indexes)
            if last_filter_found is not None:
                dot.edge(last_filter_found,
                         f"out {out}", label=edge_label(inp_name))
        if path is not None:
            dot.render(path, view=view)
        else:
            dot.render(self.name, view=view)
        return dot
