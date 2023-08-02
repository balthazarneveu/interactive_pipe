from typing import List, Optional, Callable, Dict
from core.filter import FilterCore
from core.engine import PipelineEngine

class PipelineCore:
    """A pipeline is defined as the combination of:
    - a list of filters
    - an engine to execute the filters (with cache or not)
    - optionally, some inputs to process
    """

    def __init__(self, filters: List[FilterCore], name="pipeline", cache=False, inputs: Optional[list] = None, parameters: dict = {}, global_params={}):
        if not all(isinstance(f, FilterCore) for f in filters):
            raise ValueError(
                "All elements in 'filters' must be instances of 'Filter'.")
        self.filters = filters
        self.engine = PipelineEngine(cache, safe_input_buffer_deepcopy=True)
        self.global_params = global_params
        for filter in self.filters:
            # link each filter to global params
            filter.global_params = self.global_params
            filter.reset_cache()
        self.inputs = inputs
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
    