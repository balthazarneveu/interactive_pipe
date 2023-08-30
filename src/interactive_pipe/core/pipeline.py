from typing import List, Optional, Callable, Dict
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
            filter.reset_cache()
        self.inputs = inputs
        if outputs is None:
            outputs = self.filters[-1].outputs
            logging.warning(f"Using last filter outputs {self.filters[-1]} {outputs}")
            
        self.outputs = outputs # output indexes (routing)
        # You need to set the values to their default_value for each filter
        self.parameters = parameters

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

        