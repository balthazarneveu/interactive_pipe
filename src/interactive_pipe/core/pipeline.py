from typing import List, Optional, Dict
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.engine import PipelineEngine
import logging

class PipelineCore:
    """A pipeline is defined as the combination of:
    - a list of filters
    - an engine to execute the filters (with cache or not)
    - optionally, some inputs to process
    """

    def __init__(self, filters: List[FilterCore], name="pipeline", cache=False, inputs: Optional[list] = None, parameters: dict = {}, global_params={}, outputs:  Optional[list]=None):
        if not all(isinstance(f, FilterCore) for f in filters):
            raise ValueError(
                f"All elements in 'filters' must be instances of 'Filter'. {[type(f) for f in filters]}")
        self.filters = filters
        self.engine = PipelineEngine(cache, safe_input_buffer_deepcopy=True)
        self.global_params = global_params
        for filter in self.filters:
            # link each filter to global params
            filter.global_params = self.global_params
        self.reset_cache()
        self.__initialized_inputs = False
        self.inputs = inputs
        if outputs is None:
            outputs = self.filters[-1].outputs
            logging.warning(f"Using last filter outputs {self.filters[-1]} {outputs}")
            
        self.outputs = outputs # output indexes (routing)
        # You need to set the values to their default_value for each filter
        self.parameters = parameters
        self.results = None
        self.name = name

    def reset_cache(self):
        for filter in self.filters:
            filter.reset_cache()

    def run(self) -> list:
        """Useful for standalone python acess without gui or disk write
        """
        return self.engine.run(self.filters, self.inputs)
    
    @property
    def parameters(self):
        parameters = {}
        for filt in self.filters:
            parameters[filt.name] = filt.values
        return parameters
    
    @parameters.setter
    def parameters(self, new_parameters: Dict[str, any]):
        """Force tuning parameters

        ```
        new_parameters = {
            'filter1' : {'param1_1': 5, 'param1_2': 10},
            'filter2' : {'param2_1':8}
        }
        ```
        filter1.values = new_parameters["filter1"]
        filter2.values = new_parameters["filter2"]

        scan all new_parameters, check if the key describe the name of an avaiable filter,
        then update that given filter parameters.

        assume filter2 needed a second parameter `param2_2` which was defined when instantiating the filter...
        `param2_2` will stay untouched
        """
        available_filters_names = [filt.name for filt in self.filters]
        for filter_name in new_parameters.keys():
            assert filter_name in available_filters_names, f"filter {filter_name} does not exist {available_filters_names}"
            self.filters[available_filters_names.index(filter_name)].values = new_parameters[filter_name]
    

    @property
    def inputs(self):
        assert self.__initialized_inputs, "Cannot access unitialized inputs!"
        return self.__inputs
    
    @inputs.setter
    def inputs(self, inputs: list):
        if inputs is not None:
            self.__inputs = list(inputs) if not isinstance(inputs, list) else inputs
            if len(self.__inputs) == 0:
                self.__inputs = None # similar to having no input, but explicitly saying that we have initialized it.
            self.__initialized_inputs = True
        else:
            self.__initialized_inputs = False

    def graph_representation(self, path=None, ortho=True, view=False):
        def find_previous_key(searched_out):
            last_filter_found = None
            inp_name = None
            for inp in input_indexes:
                if searched_out == inp:
                    last_filter_found = f"{inp}"
                    inp_name = f"{inp}"
            for prev_idx in range(idx):
                filt_prev = self.filters[prev_idx]
                for inp in filt_prev.outputs:
                    if searched_out == inp:
                        last_filter_found = filt_prev.name
                        inp_name = f"{inp}"
            return last_filter_found, inp_name
        def edge_label(label):
            return f"[{label}]"
        try:
            import graphviz
        except Exception as exc:
            logging.warning("cannot generate pipeline graph, need to install graphviz")
            logging.warning(exc)
            return None

        dot = graphviz.Digraph(comment=self.name)
        if ortho:
            dot.attr(splines="ortho")
        
        
        with dot.subgraph(name='cluster_in') as inputs_graph:
            inputs_graph.attr(style="dashed", color="gray", label="Inputs")
            input_indexes = list(range(len(self.inputs)))
            for inp in input_indexes:
                inputs_graph.node(f"{inp}", f"🖴 {inp}",  shape="rect", color="gray", styleItem="dash")

        with dot.subgraph(name='cluster_filters') as filter_graphs:
            # filter_graphs.attr(color="transparent",)
            filter_graphs.attr(color="gray", style="dashed", label=self.name)
            for filt in self.filters:
                all_params = []
                for pa_name, pa_val in filt.values.items():
                    all_params.append(f"\n✔️ {pa_name}")
                filter_graphs.node(filt.name, f"⚙️ {filt.name}" + ("".join(all_params)), shape="rect")        
            for idx, filt in enumerate(self.filters):
                if filt.outputs is None:
                    continue
                for out in filt.inputs:
                    last_filter_found, inp_name = find_previous_key(out)
                    if last_filter_found is not None:
                        dot.edge(last_filter_found, filt.name, label=edge_label(inp_name))
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
                out_graph.node(f"out {out}", f"🛢️ {out}", shape="rect", color="gray")
        for out in out_list:
            last_filter_found, inp_name = find_previous_key(out)
            if last_filter_found is not None:
                dot.edge(last_filter_found, f"out {out}", label=edge_label(inp_name))
        if path is not None:
            dot.render(path, view=view)
        else:
            dot.render(self.name, view=view)
        return dot
