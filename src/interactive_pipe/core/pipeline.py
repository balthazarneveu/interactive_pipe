import difflib
import logging
from typing import Any, Dict, List, Optional, Union

from interactive_pipe.core.context import REMOVED_CONTEXT_ALIASES, _set_user_context
from interactive_pipe.core.context_tracking import GRAPH_CACHE_MODES, ContextTracker
from interactive_pipe.core.engine import PipelineEngine, RunReport
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
        safe_input_buffer_deepcopy: Optional[bool] = None,
        readonly_inputs: bool = True,
        **kwargs,
    ):
        if not all(isinstance(f, FilterCore) for f in filters):
            raise ValueError(f"All elements in 'filters' must be instances of 'Filter'. {[type(f) for f in filters]}")
        self.filters = filters
        self.engine = PipelineEngine(
            cache, safe_input_buffer_deepcopy=safe_input_buffer_deepcopy, readonly_inputs=readonly_inputs
        )

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
            if not self.filters:
                raise ValueError(
                    f"pipeline '{name}' calls no filter and returns nothing: there is nothing to run or display. "
                    "Call at least one filter in its body, e.g. `out = my_filter(img)` then `return out`"
                )
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

    def invalidate_event_readers(self, event_names) -> None:
        """Force the recomputation of the filters reading the given key-bound events.

        Readers are recorded at runtime by the `events` proxy. Filters downstream
        of a reader follow automatically (sequential cache: everything after it;
        graph cache: its dependents). When an event has no known reader yet (first
        press before any filter looked at it) the whole cache is reset instead.
        """
        readers = set()
        for event_name in event_names:
            known_readers = self.framework_state.event_readers.get(event_name)
            if not known_readers:
                self.reset_cache()
                return
            readers |= known_readers
        for filt in self.filters:
            if filt.name in readers and filt.cache_mem is not None:
                filt.cache_mem.force_change = True

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

    @property
    def last_run_report(self) -> Optional[RunReport]:
        """Per-filter timings of the last run (None before the first run)."""
        return self.engine.last_run_report

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
        """Current parameters of every filter, as {filter_name: {param: value}}.

        The returned mapping is a shallow copy: mutating it does not alter the
        filters; assign it back to ``parameters`` to apply changes.
        """
        return {filt.name: dict(filt.values) for filt in self.filters}

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
        # validate everything first: a rejected update must leave the pipeline untouched
        for filter_name, filter_parameters in new_parameters.items():
            if filter_name not in available_filters_names:
                close = difflib.get_close_matches(str(filter_name), available_filters_names, n=1)
                hint = f" Did you mean '{close[0]}'?" if close else ""
                raise ValueError(f"filter {filter_name} does not exist {available_filters_names}.{hint}")
            if not isinstance(filter_parameters, dict):
                raise TypeError(
                    f"parameters of filter '{filter_name}' must be a dict {{parameter: value}}, "
                    f"got {type(filter_parameters).__name__}"
                )
            known = getattr(self.filters[available_filters_names.index(filter_name)], "_kwargs_names", None)
            if not isinstance(known, dict):
                continue
            for parameter_name in filter_parameters:
                if parameter_name not in known:
                    close = difflib.get_close_matches(str(parameter_name), list(known), n=1)
                    hint = f" Did you mean '{close[0]}'?" if close else ""
                    raise ValueError(
                        f"filter '{filter_name}' has no parameter '{parameter_name}'.{hint} "
                        f"Available parameters: {', '.join(known) or 'none'}"
                    )
        for filter_name, filter_parameters in new_parameters.items():
            self.filters[available_filters_names.index(filter_name)].values = filter_parameters

    @property
    def inputs(self):
        if not self.__initialized_inputs:
            raise RuntimeError("Cannot access uninitialized inputs!")
        return self.__inputs

    def _expected_inputs(self) -> str:
        """``pipeline 'p' expects 1 input (img)`` - start of every input count error."""
        routing = list(self.inputs_routing or [])
        name = getattr(self, "name", "pipeline")
        if not routing:
            return f"pipeline '{name}' expects no input"
        plural = "input" if len(routing) == 1 else "inputs"
        return f"pipeline '{name}' expects {len(routing)} {plural} ({', '.join(str(item) for item in routing)})"

    @inputs.setter
    def inputs(self, inputs: list):
        if inputs is not None:
            if isinstance(inputs, dict):
                provided_keys = list(inputs.keys())
                missing = [input_name for input_name in self.inputs_routing if input_name not in provided_keys]
                if missing:
                    raise ValueError(
                        f"{self._expected_inputs()}, the inputs dict is missing {', '.join(map(str, missing))} "
                        f"(provided keys: {', '.join(map(str, provided_keys)) or 'none'})"
                    )
                self.__inputs = inputs
            elif isinstance(inputs, (list, tuple)):
                # inputs is a list or a tuple
                if len(inputs) != len(self.inputs_routing):
                    raise ValueError(f"{self._expected_inputs()}, got {len(inputs)}")
                self.__inputs = {}
                for idx, input_name in enumerate(self.inputs_routing):
                    self.__inputs[input_name] = inputs[idx]
            else:
                # single element
                if len(self.inputs_routing) != 1:
                    raise ValueError(f"{self._expected_inputs()}, got 1")
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
                raise ValueError(f"{self._expected_inputs()}, got 0")
            self.__inputs = None
        self.__initialized_inputs = True
        self.reset_cache()
