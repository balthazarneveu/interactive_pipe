from typing import List, Optional, Callable, Dict
from core.filter import FilterCore
from core.engine import PipelineEngine

class PipelineCore:
    """A pipeline is defined as the combination of:
    - a list of filters
    - an engine to execute the filters (with cache or not)
    - optinally, some inputs to process
    """

    def __init__(self, filters: List[FilterCore], name="pipeline", cache=False, inputs: Optional[list] = None, parameters: dict = {}):
        if not all(isinstance(f, FilterCore) for f in filters):
            raise ValueError(
                "All elements in 'filters' must be instances of 'Filter'.")
        self.filters = filters
        self.engine = PipelineEngine(cache, safe_input_buffer_deepcopy=True)
        self.parameters = parameters
        for filter in self.filters:
            filter.set_global_params(self.parameters)
            filter.reset_cache()
        self.inputs = inputs
        # You need to set the values to their default_value
        if parameters is not None:
            self.set_parameters(parameters)

    def run(self) -> list:
        """Useful for standalone python acess without gui or disk write
        """
        return self.engine.run(self.filters, self.inputs)

    def set_parameters(self, parameters: Dict[str, any]):
        """Force tuning parameters
        """
        for pa in self.filters:
            if pa.name in parameters.keys():
                # directly set from the dictionary
                pa.values = parameters[pa.name]
            else:
                # FIXME: there's a very ugly mapping between slider_values (a list) & values (dictionary)
                for idx, _pa_name in enumerate(pa.sliderslist):
                    pa.values[list(pa.values.keys())[idx]
                              ] = pa.defaultvalue[idx]
        self.parameters = parameters
        # for each slider, transmit global parameters
        for slider in self.filters:
            slider.set_global_params(parameters)