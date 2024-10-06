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

    def __init__(
        self,
        filters: List[FilterCore],
        name="pipeline",
        cache=False,
        inputs: Optional[list] = None,
        parameters: dict = {},
        global_params: Optional[dict] = None,
        global_parameters: Optional[dict] = None,  # alias for global_params
        global_state: Optional[dict] = None,  # alias for global_params
        global_context: Optional[dict] = None,  # alias for global_params
        context: Optional[dict] = None,  # alias for global_params
        state: Optional[dict] = None,  # alias for global_params
        outputs:  Optional[list] = None,
        safe_input_buffer_deepcopy: bool = True
    ):
        if not all(isinstance(f, FilterCore) for f in filters):
            raise ValueError(
                f"All elements in 'filters' must be instances of 'Filter'. {[type(f) for f in filters]}")
        self.filters = filters
        self.engine = PipelineEngine(
            cache, safe_input_buffer_deepcopy=safe_input_buffer_deepcopy)
        if global_parameters is not None:
            global_params = global_parameters
        elif global_context is not None:
            global_params = global_context
        elif global_state is not None:
            global_params = global_state
        elif state is not None:
            global_params = state
        elif context is not None:
            global_params = context
        if global_params is None:
            global_params = {}
        self.global_params = global_params
        for filter in self.filters:
            # link each filter to global params
            filter.global_params = self.global_params
        self.reset_cache()
        if inputs is None:
            logging.warning(
                "Setting a pipeline without input -  use inputs=[] to get rid of this warning")
            self.inputs_routing = []
        else:
            self.inputs_routing = inputs

        self.__initialized_inputs = False
        if outputs is None:
            outputs = self.filters[-1].outputs
            logging.warning(
                f"Using last filter outputs {self.filters[-1]} {outputs}")

        self.outputs = outputs  # output indexes (routing)
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
        return self.engine.run(self.filters, imglst=self.inputs)

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
            assert filter_name in available_filters_names, f"filter {filter_name}" + \
                f"does not exist {available_filters_names}"
            self.filters[available_filters_names.index(
                filter_name)].values = new_parameters[filter_name]

    @property
    def inputs(self):
        assert self.__initialized_inputs, "Cannot access unitialized inputs!"
        return self.__inputs

    @inputs.setter
    def inputs(self, inputs: list):
        if inputs is not None:
            if isinstance(inputs, dict):
                provided_keys = list(inputs.keys())
                for idx, input_name in enumerate(self.inputs_routing):
                    assert input_name in provided_keys, f"{input_name} is not among {provided_keys}"
                self.__inputs = inputs
            elif isinstance(inputs, list) or isinstance(inputs, tuple):
                # inputs is a list or a tuple
                assert len(inputs) == len(
                    self.inputs_routing), f"wrong amount of inputs\nprovided {len(inputs)}" + \
                    f"inputs vs expected:{len(self.inputs_routing)}"
                self.__inputs = {}
                for idx, input_name in enumerate(self.inputs_routing):
                    self.__inputs[input_name] = inputs[idx]
            else:
                # single element
                assert len(self.inputs_routing) == 1
                self.__inputs = {self.inputs_routing[0]: inputs}
            assert isinstance(self.__inputs, dict)
            if len(self.__inputs.keys()) == 0:
                # similar to having no input, but explicitly saying that we have initialized it.
                self.__inputs = None
        else:
            assert self.inputs_routing is None or ((isinstance(self.inputs_routing, tuple) or isinstance(
                self.inputs_routing, list)) and len(self.inputs_routing) == 0)
            self.__inputs = None
        self.__initialized_inputs = True
        self.reset_cache()
