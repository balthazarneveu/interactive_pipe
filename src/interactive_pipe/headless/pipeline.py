import difflib
import logging
from pathlib import Path
from typing import Any, Callable, List, Optional

from interactive_pipe.core.filter import FilterCore, analyze_apply_fn_signature
from interactive_pipe.core.graph import PipelineSyntaxError, get_call_graph
from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl


class HeadlessPipeline(PipelineCore):
    """PipelineCore extensions - saving/loading to disk - graphs - init from interpreted functions

    Adds some powerful features to the pipeline core such as:
    - creating a pipeline from a function as a sequential filter
    - importing/exporting parameters ("tuning") as json or yaml
    - saving output images
    - printing current parameters in the terminal
    - graph representation
    """

    controls: List[Control]  # List of controls connected to filters

    @property
    def parameters(self):
        """Get current parameters from all filters"""
        return super().parameters

    @parameters.setter
    def parameters(self, new_parameters):
        """Override to also update control values when parameters are set"""
        # Call parent setter to update filter values using the descriptor protocol
        PipelineCore.parameters.__set__(self, new_parameters)
        # Update control values to match the new parameters
        if hasattr(self, "controls"):
            for ctrl in self.controls:
                if ctrl.filter_to_connect is not None:
                    filter_name = ctrl.filter_to_connect.name
                    param_name = ctrl.parameter_name_to_connect
                    if filter_name in new_parameters and param_name in new_parameters[filter_name]:
                        ctrl.value = new_parameters[filter_name][param_name]

    @staticmethod
    def routing_indexes(inputs_names, all_variables):
        if not inputs_names:
            return None
        return [all_variables[input_name] for input_name in inputs_names]

    @classmethod
    def from_function(cls, pipe: Callable[..., Any], inputs=None, *, _routing_by_indexes=False, **kwargs):
        if not isinstance(pipe, Callable):
            raise TypeError(f"pipe must be Callable, got {type(pipe)}")
        graph = get_call_graph(pipe)
        all_variables = {}
        total_index = 0
        function_inputs = {}
        input_routing = []
        for input_index, input_name in enumerate(graph["args"]):
            all_variables[input_name] = total_index
            function_inputs[input_name] = total_index
            if _routing_by_indexes:
                input_routing.append(total_index)
            else:
                input_routing.append(input_name)
            total_index += 1
        for filt_dict in graph["call_graph"]:
            for key in ["args", "returns"]:
                for variable_name in filt_dict[key] or []:
                    if variable_name not in all_variables:
                        all_variables[variable_name] = total_index
                        total_index += 1

        filters = []
        filters_count = {}
        filters_names = []
        bindings = []  # (filter, parameter name, control), connected once names are resolved
        seen_function_ids = set()
        for filt_dict in graph["call_graph"]:
            # avoid duplicate filters names
            filt_name = filt_dict["function_name"]
            filter_count = filters_count.get(filt_name, -1)
            if filter_count >= 0:
                filters_count[filt_name] += 1
                filt_name = filt_name + f"_{filters_count[filt_name]}"
            else:
                filters_count[filt_name] = 0
            if _routing_by_indexes:
                inputs_filt = HeadlessPipeline.routing_indexes(filt_dict["args"], all_variables)
                outputs_filt = HeadlessPipeline.routing_indexes(filt_dict["returns"], all_variables)
            else:
                inputs_filt = filt_dict["args"]
                outputs_filt = filt_dict["returns"]
            logging.debug(f"-----------------> {filt_name} {inputs_filt} {outputs_filt}")
            if isinstance(filt_dict["function_object"], FilterCore):
                filt = filt_dict["function_object"]
                filt.inputs = inputs_filt
                filt.outputs = outputs_filt
                filt.name = filt_name
                # EnhancedFilterCore (filter_from_function) carries its controls; a plain FilterCore has none
                params_to_analyze = dict(getattr(filt, "controls", None) or {})
            else:
                # when using the @interactive decorator
                filt = FilterCore(
                    name=filt_name,
                    inputs=inputs_filt,
                    outputs=outputs_filt,
                    apply_fn=filt_dict["function_object"],
                    inplace=bool(getattr(filt_dict["function_object"], "__interactive_pipe_inplace__", False)),
                )
                func_kwargs = analyze_apply_fn_signature(filt_dict["function_object"])[1]
                if id(filt_dict["function_object"]) not in seen_function_ids:
                    registered_controls = Control.get_controls(filt_dict["function_object"])
                else:
                    # Repeated filter: the registered Control objects already
                    # drive the first instance, so each repeat gets clones
                    # suffixed like the filter name ("amount" -> "amount_1").
                    # Key/timer-bound controls are not cloned - their key
                    # bindings would collide - so repeats run those with
                    # default values.
                    instance_suffix = f"_{filters_count[filt_dict['function_name']]}"
                    registered_controls = {
                        param_name: ctrl._clone_unconnected(ctrl.name + instance_suffix)
                        for param_name, ctrl in Control.get_controls(filt_dict["function_object"]).items()
                        if not isinstance(ctrl, (KeyboardControl, TimeControl))
                    }
                params_to_analyze = {**func_kwargs, **registered_controls}
            # Literal keyword arguments in the pipeline body (`amplify(img, gain=2.5)`)
            # set this instance's value; a bound control gets a per-instance clone
            # with that default so the shared registered control is never mutated.
            literal_kwargs = filt_dict.get("kwargs") or {}
            for param_name, literal_value in literal_kwargs.items():
                bound_control = params_to_analyze.get(param_name)
                if isinstance(bound_control, Control):
                    try:
                        params_to_analyze[param_name] = bound_control._clone_with_default(literal_value)
                    except (TypeError, ValueError) as exc:
                        raise PipelineSyntaxError(
                            f"invalid value for '{param_name}' of filter '{filt_dict['function_name']}': {exc}",
                            hint="use a value accepted by the control, or change the control declaration",
                            **filt_dict.get("location", {}),
                        ) from None
            for param_name, param_value in params_to_analyze.items():
                if isinstance(param_value, Control):
                    bindings.append((filt, param_name, param_value))
            filt.values = {
                param_name: literal_value
                for param_name, literal_value in literal_kwargs.items()
                if not isinstance(params_to_analyze.get(param_name), Control)
            }
            filters.append(filt)
            filters_names.append(filt_name)
            seen_function_ids.add(id(filt_dict["function_object"]))
        logging.debug(filters_count)
        logging.debug(filters_names)

        bindings = cls._disambiguate_control_names(bindings)
        control_list = []
        for filt, param_name, ctrl in bindings:
            ctrl.connect_filter(filt, param_name)
            filt.values = {param_name: ctrl.value_default}
            control_list.append(ctrl)

        # GUI widgets are keyed by control name: distinct controls sharing a
        # name within one pipeline would silently drive the wrong filter.
        controls_by_name = {}
        for ctrl in control_list:
            previous = controls_by_name.get(ctrl.name)
            if previous is not None and previous is not ctrl:
                raise ValueError(
                    f"Duplicate control name '{ctrl.name}' in pipeline '{pipe.__name__}': "
                    "control names must be unique within a pipeline. "
                    "Pass name=... to one of the controls to disambiguate."
                )
            controls_by_name[ctrl.name] = ctrl

        # Helper function to convert nested output names to indexes
        def convert_outputs_to_indexes(output_structure):
            if isinstance(output_structure, str):
                return all_variables[output_structure]
            elif isinstance(output_structure, list):
                return [convert_outputs_to_indexes(item) for item in output_structure]
            else:
                return output_structure

        if _routing_by_indexes:
            outputs = convert_outputs_to_indexes(graph["returns"])
        else:
            outputs = graph["returns"]
        if len(function_inputs) == 0 and inputs is None:
            logging.info("Auto deduced that there are no arguments provided to the function")
        data_class = cls(
            filters=filters,
            name=graph["function_name"],
            inputs=input_routing,
            outputs=outputs,
            **kwargs,
        )
        data_class.controls = control_list
        return data_class

    @staticmethod
    def _disambiguate_control_names(bindings: list) -> list:
        """Rename auto-named controls whose name collides with another control of the pipeline.

        Two filters each declaring a ``gain`` control is the normal case: every
        auto-named control bound to a colliding parameter name becomes
        ``"<filter>.<param>"`` (``amplify.gain``, ``blend.gain``; a repeated
        filter's ``gain_1`` becomes ``amplify_1.gain``), so the widget label
        says which filter it drives and matches
        ``parameters={"<filter>": {"<param>": value}}``. Repeats of a single
        filter without any other collision keep the ``gain``, ``gain_1``
        suffixes. Controls named explicitly (``name=...``) are never renamed;
        if they still collide, the caller raises.

        Renamed controls are per-pipeline clones: the registered control
        shared by every pipeline using the filter is never mutated, and
        building the same pipeline twice gives the same names.
        """
        by_name: dict = {}
        for binding in bindings:
            ctrl = binding[2]
            group = by_name.setdefault(ctrl.name, [])
            if all(other[2] is not ctrl for other in group):
                group.append(binding)
        colliding_params = set()
        for group in by_name.values():
            if len(group) < 2:
                continue
            for _filt, param_name, ctrl in group:
                if ctrl._auto_named:
                    colliding_params.add(param_name)
        if not colliding_params:
            return bindings
        renamed = []
        for filt, param_name, ctrl in bindings:
            if ctrl._auto_named and param_name in colliding_params:
                ctrl = ctrl._clone_unconnected(f"{filt.name}.{param_name}")
            renamed.append((filt, param_name, ctrl))
        return renamed

    def export_tuning(self, path: Optional[Path] = None, override=False) -> None:
        """Export the current parameters of every filter to a json/yaml file"""
        if path is not None:
            Parameters(self.parameters).save(path, override=override)

    def import_tuning(self, path: Optional[Path] = None) -> None:
        """Open a json/yaml tuning file and set parameters"""
        try:
            self.parameters = Parameters.from_file(path).data
        except Exception:
            # Broad on purpose: best-effort load, a corrupt/missing tuning file
            # must not crash the app (bound to a GUI key).
            logging.exception(f"Cannot load parameters from {path}")

    def __repr__(self):
        """Describe filters routing and tuning parameters"""
        ret = "\n".join(repr(filt) for filt in self.filters)
        ret += "\n{\n"
        for sl in self.filters:
            ret += f"{sl.name} : {sl.values},\n"
        ret = ret[:-2] + "\n"  # remove comma for yaml
        ret += "}"
        return ret

    def update_parameters_from_controls(self):
        if not hasattr(self, "controls"):
            # Not having .controls attribute
            # This happens for headless pipelines which have no list of controls
            return
        # Merge control values into existing parameters instead of replacing
        current_params = self.parameters  # Get current parameters
        for ctrl in self.controls:
            if ctrl.filter_to_connect is None or ctrl.parameter_name_to_connect is None:
                continue
            logging.debug(f"{ctrl.filter_to_connect.name}, {ctrl.parameter_name_to_connect}, {ctrl.value}")
            current_params.setdefault(ctrl.filter_to_connect.name, {})[ctrl.parameter_name_to_connect] = ctrl.value
        # Assign once, after every control has been merged, and to the filters only:
        # the HeadlessPipeline setter also writes the values back into the controls,
        # which would overwrite a control changed meanwhile (GUI thread while a
        # threaded run reads them, or not-yet-merged controls after a GUI reset).
        PipelineCore.parameters.__set__(self, current_params)  # type: ignore[attr-defined]

    def __run(self):
        self.update_parameters_from_controls()
        result_full = super().run()
        output_indexes = self.outputs if self.outputs is not None else self.filters[-1].outputs
        if not output_indexes:
            return None
        if isinstance(output_indexes[0], list):
            # 2D layout: keep None placeholders so (row, col) positions stay aligned
            # with self.outputs (empty cells are skipped by the GUI)
            return [
                [None if out_index is None else result_full.get(out_index) for out_index in row]
                for row in output_indexes
                if isinstance(row, (list, tuple))
            ]
        return tuple(result_full[idx] for idx in output_indexes if idx in result_full)

    def run(self):
        self.results = self.__run()
        return self.results

    def save(
        self,
        path: Optional[Path] = None,
        data_wrapper_fn: Optional[Callable[..., Any]] = None,
        output_indexes: Optional[list] = None,
        save_entire_buffer=False,
    ) -> Optional[Path]:
        """Save images"""
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
        if path is None:
            raise ValueError("path must be provided for saving")
        if not isinstance(path, Path):
            path = Path(path)
        self.export_tuning(path.with_suffix(".yaml"))
        if not isinstance(result_full, dict):
            raise RuntimeError(f"Expected dict from pipeline run, got {type(result_full)}")
        for num, res_current in result_full.items():
            if output_indexes is not None and num not in output_indexes:
                continue
            current_name = path.with_name(path.stem + "_" + str(num) + path.suffix)
            if res_current is not None and not (isinstance(res_current, list) and len(res_current) == 0):
                try:
                    to_save = data_wrapper_fn(res_current) if data_wrapper_fn is not None else res_current
                    if not hasattr(to_save, "save"):
                        raise AttributeError(f"Result object {type(to_save)} has no 'save' method")
                    to_save.save(current_name)  # type: ignore
                except Exception:
                    # Broad on purpose: one failed output must not abort the
                    # whole batch save; continue with the remaining outputs.
                    logging.exception(f"Cannot save image {current_name}")
            # @ TODO: handle proper output suffixes namings
            logging.info(f"saved image {current_name}")
        return path

    def parameters_from_keyword_args(self, **kwargs) -> dict:
        """Map ``pipeline(img, gain=2.0)`` keyword arguments to ``{filter: {param: value}}``.

        A keyword sets the parameter of that name in every filter that has one
        (to target a single filter, use ``parameters={"filter": {"param": value}}``).

        Raises:
            TypeError: if a keyword is not a parameter of any filter.
        """
        new_param_dict = {}
        current_parameters = self.parameters
        unknown = []
        for key, value in kwargs.items():
            matched = False
            for filter_name, parameters_dict in current_parameters.items():
                if key in parameters_dict:
                    new_param_dict.setdefault(filter_name, {})[key] = value
                    matched = True
            if not matched:
                unknown.append(key)
        if unknown:
            available = sorted({name for params in current_parameters.values() for name in params})
            message = (
                f"pipeline '{self.name}' got unexpected keyword argument(s) "
                + ", ".join(f"'{key}'" for key in unknown)
                + f". Available parameters: {', '.join(available) or 'none'}"
                + " (reserved keywords: inputs, parameters, context)."
            )
            suggestions = [
                f"'{key}' -> '{match[0]}'"
                for key in unknown
                for match in [difflib.get_close_matches(key, available, n=1)]
                if match
            ]
            if suggestions:
                message += " Did you mean " + ", ".join(suggestions) + "?"
            raise TypeError(message)
        return new_param_dict

    def __call__(self, *inputs_tuple, inputs=None, parameters=None, context=None, **kwargs) -> Any:
        # validated first: an unknown keyword raises before anything is changed
        kwargs_params = self.parameters_from_keyword_args(**kwargs)
        if inputs is not None:
            if not isinstance(inputs, dict):
                raise TypeError(f"inputs must be a dict, got {type(inputs)}")
            self.inputs = inputs  # type: ignore
            logging.debug(f"Dict style inputs {list(inputs.keys())}")
        else:
            # the inputs setter validates the count against inputs_routing
            self.inputs = list(inputs_tuple) if inputs_tuple else None  # type: ignore
        # Handle context parameter - update user context if provided
        self.update_user_context(context)
        # Only update self.parameters if parameters argument is explicitly provided
        if parameters is not None:
            self.parameters = parameters
        # Merge in any keyword arguments as parameters
        if kwargs_params:
            # Get current parameters, merge, and re-set to trigger the setter
            current_params = self.parameters  # Calls getter
            for filter_name, params in kwargs_params.items():
                if filter_name not in current_params:
                    current_params[filter_name] = {}
                current_params[filter_name].update(params)
            self.parameters = current_params  # Calls setter to apply to filters
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
                        logging.debug(f"{searched_out}, {filt_prev.name} {inp}")
                    if searched_out == inp:
                        last_filter_found = filt_prev.name
                        inp_name = f"{inp}"
            return last_filter_found, inp_name

        def edge_label(label):
            return f"[{label}]"

        graphviz_hint = (
            "Graphviz executables not found. Please install Graphviz system package:\n"
            "  - Ubuntu/Debian: sudo apt-get install graphviz\n"
            "  - macOS: brew install graphviz\n"
            "  - Windows: Download from https://graphviz.org/download/"
        )
        try:
            import graphviz
        except ImportError as exc:
            logging.warning("cannot generate pipeline graph, need to install graphviz")
            logging.warning(exc)
            return None

        # Try to import ExecutableNotFound, but handle if it's not available
        try:
            from graphviz.backend.execute import ExecutableNotFound
        except (ImportError, AttributeError):
            ExecutableNotFound = None

        dot = graphviz.Digraph(comment=self.name)
        if ortho:
            dot.attr(splines="ortho")
        if self.inputs_routing is None:
            raise ValueError("Cannot plot graph: input routing is not provided")
        input_indexes = self.inputs_routing
        with dot.subgraph(name="cluster_in") as inputs_graph:  # type: ignore[reportAssignmentType]
            inputs_graph.attr(style="dashed", color="gray", label="Inputs")  # type: ignore[reportAttributeAccessIssue]
            for inp in input_indexes:
                inputs_graph.node(f"{inp}", f"🖴 {inp}", shape="rect", color="gray", styleItem="dash")  # type: ignore[reportAttributeAccessIssue]

        with dot.subgraph(name="cluster_filters") as filter_graphs:  # type: ignore[reportAssignmentType]
            # filter_graphs.attr(color="transparent",)
            filter_graphs.attr(color="gray", style="dashed", label=self.name)  # type: ignore[reportAttributeAccessIssue]
            for filt in self.filters:
                all_params = []
                for pa_name, pa_val in filt.values.items():
                    all_params.append(f"\n✔️ {pa_name}")
                filter_graphs.node(filt.name, f"⚙️ {filt.name}" + ("".join(all_params)), shape="rect")  # type: ignore[reportAttributeAccessIssue]
            for idx, filt in enumerate(self.filters):
                if filt.inputs is None:
                    continue
                for out in filt.inputs:
                    last_filter_found, inp_name = find_previous_key(out, idx, input_indexes)
                    if last_filter_found is not None:
                        dot.edge(last_filter_found, filt.name, label=edge_label(inp_name))
        out_list = []
        if self.outputs is None:
            raise ValueError("Cannot generate graph: outputs not defined")
        for out_item in self.outputs:
            out_row = out_item
            if not isinstance(out_item, (list, tuple)):
                out_row = [out_item]
            for out in out_row:
                if out is None:
                    continue
                out_list.append(out)
        with dot.subgraph(name="cluster_out") as out_graph:  # type: ignore[reportAssignmentType]
            out_graph.attr(style="dashed", color="gray", label="Outputs")  # type: ignore[reportAttributeAccessIssue]
            for out in out_list:
                out_graph.node(f"out {out}", f"🛢️ {out}", shape="rect", color="gray")  # type: ignore[reportAttributeAccessIssue]
        for out in out_list:
            last_filter_found, inp_name = find_previous_key(out, len(self.filters), input_indexes)
            if last_filter_found is not None:
                dot.edge(last_filter_found, f"out {out}", label=edge_label(inp_name))
        try:
            if path is not None:
                dot.render(path, view=view)
            else:
                dot.render(self.name, view=view)
        except Exception as exc:
            # Broad on purpose: graph rendering is a best-effort extra; the
            # string matching below handles ExecutableNotFound even when the
            # optional import above failed.
            exc_type_name = type(exc).__name__
            if (ExecutableNotFound and isinstance(exc, ExecutableNotFound)) or "ExecutableNotFound" in exc_type_name:
                logging.error(graphviz_hint)
            else:
                logging.error(f"Failed to render graph: {exc}")
            return None
        return dot
