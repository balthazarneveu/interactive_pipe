import logging
from typing import Any, Dict, List, Optional, Union

from interactive_pipe.core.context import REMOVED_CONTEXT_ALIASES, _set_user_context
from interactive_pipe.core.context_tracking import GRAPH_CACHE_MODES, ContextTracker
from interactive_pipe.core.engine import PipelineEngine
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.framework_state import FrameworkState


class PipelineCore:
    """A pipeline is defined as the combination of:
    - a list of filters
    - an engine to execute the filters (with cache or not)
    - optionally, some inputs to process

    cache modes:
    - False: recompute everything on every run
    - True: sequential prefix cache (a parameter change recomputes every filter after it)
    - "graph": dependency-aware cache (only the filters actually affected by a change
      are recomputed, including dependencies through the shared `context`)
    - "graph-strict": like "graph", plus context reads return numpy arrays as read-only
      views so accidental in-place mutation raises at the offending line
    """

    def __init__(
        self,
        filters: List[FilterCore],
        name="pipeline",
        cache: Union[bool, str] = False,
        inputs: Optional[list] = None,
        parameters: Optional[dict] = None,
        context: Optional[dict] = None,
        outputs: Optional[list] = None,
        safe_input_buffer_deepcopy: bool = True,
        **kwargs,
    ):
        if not all(isinstance(f, FilterCore) for f in filters):
            raise ValueError(f"All elements in 'filters' must be instances of 'Filter'. {[type(f) for f in filters]}")
        self.filters = filters
        self.engine = PipelineEngine(cache, safe_input_buffer_deepcopy=safe_input_buffer_deepcopy)

        # Reject removed aliases of the 'context' parameter with a clear message
        for alias in REMOVED_CONTEXT_ALIASES:
            if alias in kwargs:
                raise TypeError(
                    f"'{alias}' argument was removed in interactive_pipe 0.9.0; pass context={{...}} instead."
                )

        # Warn about any remaining unknown kwargs
        if kwargs:
            unknown = ", ".join(kwargs.keys())
            raise TypeError(f"PipelineCore.__init__() got unexpected keyword argument(s): {unknown}")

        if context is None:
            context = {}
        # property setter links every filter to the shared dict and, in graph cache
        # mode, wraps it in a ContextTracker (class filters access it as self.global_params)
        self.global_params = context
        self.framework_state = FrameworkState()
        self.framework_state.pipeline = self
        for filt in self.filters:
            # link each filter to the shared framework state
            # (global_params linking is handled by the property setter)
            filt.framework_state = self.framework_state

        # Initialize user context (separate from global_params for clean API)
        self._user_context = dict(context) if isinstance(context, dict) else {}
        if self._graph_cache_mode:
            # dependency-aware cache: track context reads/writes per filter so
            # context-based data dependencies invalidate the right cached results
            self._user_context = ContextTracker(self._user_context, strict=self.engine.cache == "graph-strict")
            self.engine.context_tracker = self._user_context

        self.reset_cache()
        if inputs is None:
            logging.warning("Setting a pipeline without input -  use inputs=[] to get rid of this warning")
            self.inputs_routing = []
        else:
            self.inputs_routing = inputs

        self.__initialized_inputs = False
        if outputs is None:
            outputs = self.filters[-1].outputs
            logging.warning(f"Using last filter outputs {self.filters[-1]} {outputs}")

        self.outputs = outputs  # output indexes (routing)
        # You need to set the values to their default_value for each filter
        if parameters is None:
            parameters = {}
        self.parameters = parameters
        self.results = None
        self.name = name

    def reset_cache(self):
        for filt in self.filters:
            filt.reset_cache()

    @property
    def _graph_cache_mode(self) -> bool:
        return self.engine.cache in GRAPH_CACHE_MODES

    @property
    def global_params(self):
        return self._global_params_storage

    @global_params.setter
    def global_params(self, new_global_params: dict):
        """Replace the shared dict and relink every filter to it.

        Class-based filters access this dict as ``self.global_params`` inside their
        apply method - a data channel invisible to signature or AST inspection. In
        graph cache mode the dict is wrapped in a ContextTracker so those accesses
        are attributed to the running filter like the modern ``context`` proxy.
        Replacing the shared state wholesale (e.g. gradio dry run) also invalidates
        every cached result computed from it.
        """
        if self._graph_cache_mode:
            if not isinstance(new_global_params, ContextTracker):
                new_global_params = ContextTracker(new_global_params)
            self.engine.global_params_tracker = new_global_params
            # replacing the shared state invalidates anything computed from it
            self.reset_cache()
        self._global_params_storage = new_global_params
        for filt in self.filters:
            # link each filter to global params
            filt.global_params = new_global_params

    def run(self) -> dict:
        """Useful for standalone python access without gui or disk write"""
        # Set user context before running pipeline
        _set_user_context(self._user_context)
        try:
            return self.engine.run(self.filters, imglst=self.inputs)
        finally:
            # Clear user context after execution
            _set_user_context(None)

    def update_user_context(self, context: Optional[Dict[str, Any]]) -> None:
        """Merge user-provided context into the pipeline's user context.

        The single sanctioned way to feed context in from the outside
        (GUI __call__ / pipeline __call__); does nothing when context is None.
        """
        if context is None:
            return
        if not isinstance(context, dict):
            raise TypeError(f"context must be a dict, got {type(context)}")
        self._user_context.update(context)

    def _reset_global_params(self):
        for filt in self.filters:
            filt.global_params = self.global_params
            filt.framework_state = self.framework_state

    @property
    def parameters(self):
        parameters = {}
        for filt in self.filters:
            parameters[filt.name] = filt.values
        return parameters

    @parameters.setter
    def parameters(self, new_parameters: Dict[str, Any]):
        """Force tuning parameters

        ```
        new_parameters = {
            'filter1' : {'param1_1': 5, 'param1_2': 10},
            'filter2' : {'param2_1':8}
        }
        ```
        filter1.values = new_parameters["filter1"]
        filter2.values = new_parameters["filter2"]

        scan all new_parameters, check if the key describe the name of an available filter,
        then update that given filter parameters.

        assume filter2 needed a second parameter `param2_2` which was defined when instantiating the filter...
        `param2_2` will stay untouched
        """
        available_filters_names = [filt.name for filt in self.filters]
        for filter_name in new_parameters.keys():
            if filter_name not in available_filters_names:
                raise ValueError(f"filter {filter_name} does not exist {available_filters_names}")
            self.filters[available_filters_names.index(filter_name)].values = new_parameters[filter_name]

    @property
    def inputs(self):
        if not self.__initialized_inputs:
            raise RuntimeError("Cannot access uninitialized inputs!")
        return self.__inputs

    @inputs.setter
    def inputs(self, inputs: list):
        if inputs is not None:
            if isinstance(inputs, dict):
                provided_keys = list(inputs.keys())
                for idx, input_name in enumerate(self.inputs_routing):
                    if input_name not in provided_keys:
                        raise ValueError(f"{input_name} is not among {provided_keys}")
                self.__inputs = inputs
            elif isinstance(inputs, (list, tuple)):
                # inputs is a list or a tuple
                if len(inputs) != len(self.inputs_routing):
                    raise ValueError(
                        f"Wrong amount of inputs: provided {len(inputs)} vs expected {len(self.inputs_routing)}"
                    )
                self.__inputs = {}
                for idx, input_name in enumerate(self.inputs_routing):
                    self.__inputs[input_name] = inputs[idx]
            else:
                # single element
                if len(self.inputs_routing) != 1:
                    raise ValueError(f"Single input provided but expected {len(self.inputs_routing)} inputs")
                self.__inputs = {self.inputs_routing[0]: inputs}
            if not isinstance(self.__inputs, dict):
                raise RuntimeError("Internal error: inputs should be a dict")
            if len(self.__inputs.keys()) == 0:
                # similar to having no input, but explicitly saying that we have initialized it.
                self.__inputs = None
        else:
            if not (
                self.inputs_routing is None
                or (isinstance(self.inputs_routing, (tuple, list)) and len(self.inputs_routing) == 0)
            ):
                raise ValueError("Cannot set inputs to None when inputs_routing is defined")
            self.__inputs = None
        self.__initialized_inputs = True
        self.reset_cache()
