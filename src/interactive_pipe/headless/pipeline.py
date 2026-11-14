import logging
from pathlib import Path
from typing import Any, Callable, List, Optional

import numpy as np

from interactive_pipe.core.filter import FilterCore, analyze_apply_fn_signature
from interactive_pipe.core.graph import PipelineSyntaxError, get_call_graph
from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.data_objects.data import Data
from interactive_pipe.data_objects.image import Image
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.data_objects.table import PANDAS_AVAILABLE, Table
from interactive_pipe.graphical.display import FIGURE_DPI, figure_of, release_pyplot_figure
from interactive_pipe.headless.control import Control, TimeControl
from interactive_pipe.headless.keyboard import KeyboardControl

_UNSAFE_FILENAME_CHARS = '<>:"/\\|?*'


def _safe_file_part(name: Any) -> str:
    """Output names can be call sources (``blur(amplify(img))``): keep them portable as file names."""
    text = str(name)
    for char in _UNSAFE_FILENAME_CHARS:
        text = text.replace(char, "_")
    return text


def _flatten_outputs(outputs) -> list:
    """Output names of a flat or 2D (list of rows) layout."""
    flat = []
    for item in outputs:
        if isinstance(item, (list, tuple)):
            flat.extend(_flatten_outputs(item))
        elif item is not None:
            flat.append(item)
    return flat


def _with_supported_suffix(path: Path, extensions: Optional[List[str]]) -> Path:
    if not extensions or path.suffix in extensions:
        return path
    return path.with_suffix(extensions[0])


def _as_image_array(array: np.ndarray) -> Optional[np.ndarray]:
    """``[0, 1]`` float version of an image-shaped array, None if it is not an image."""
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[..., 0]
    if not (array.ndim == 2 or (array.ndim == 3 and array.shape[-1] in (3, 4))):
        return None
    if array.dtype == np.bool_:
        return array.astype(np.float32)
    if array.dtype == np.uint8:
        return array / 255.0
    if array.dtype == np.uint16:
        return array / 65535.0
    if np.issubdtype(array.dtype, np.floating):
        return array
    return None


def _save_output(result: Any, path: Path) -> Optional[Path]:
    """Write one pipeline output in a format matching its type; None if the type is not supported."""
    if isinstance(result, Image):
        result.save(_with_supported_suffix(path, result.file_extensions))
        return result.path
    if isinstance(result, Table):
        target = _with_supported_suffix(path, result.file_extensions)
        if target.suffix == ".csv" and not PANDAS_AVAILABLE:
            target = target.with_suffix(".pkl")
        result.save(target)
        return target
    if isinstance(result, Data):
        target = _with_supported_suffix(path, result.file_extensions)
        result.save(target)
        return target
    if isinstance(result, np.ndarray):
        image = _as_image_array(result)
        if image is not None:
            wrapped = Image(image)
            extensions = wrapped.file_extensions
            if image.ndim == 3 and image.shape[-1] == 4:
                extensions = [".png", ".tif"]  # no alpha channel in jpeg
            wrapped.save(_with_supported_suffix(path, extensions))
            return wrapped.path
        if result.ndim == 1:
            target = path.with_suffix(".csv")
            np.savetxt(target, result, delimiter=",")
            return target
        target = path.with_suffix(".npy")
        np.save(target, result)
        return target
    if isinstance(result, str):
        target = path.with_suffix(".txt")
        target.write_text(result)
        return target
    figure = figure_of(result)
    if figure is not None:
        # matplotlib Figure / Axes: vector formats kept when asked for
        target = _with_supported_suffix(path, [".png", ".pdf", ".svg", ".jpg"])
        release_pyplot_figure(figure)
        figure.savefig(target, dpi=FIGURE_DPI, facecolor="white")
        return target
    return None


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
                for filt, param_name in ctrl.targets:
                    if filt.name in new_parameters and param_name in new_parameters[filt.name]:
                        ctrl.value = new_parameters[filt.name][param_name]

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
        # The pipeline owns clones of the declared controls (two pipelines built
        # from one filter never share values). One clone per share key and
        # filter instance suffix: the same declared Control object used by
        # several filters is one widget driving all of them.
        pipeline_clones: dict = {}

        def pipeline_control(declared: Control, suffix: str, filter_name: str, param_name: str) -> Control:
            key = (declared.share_key, suffix)
            clone = pipeline_clones.get(key)
            if clone is None:
                # first instance: starts from the declared control's value; repeats from the default
                clone = declared._clone_unconnected(declared.name + suffix, keep_value=not suffix)
                clone._declared_by = f"{filter_name}.{param_name}"  # type: ignore[attr-defined]
                pipeline_clones[key] = clone
            elif clone.value_default != declared.value_default:
                raise ValueError(
                    f"control '{clone.name}' is shared by {clone._declared_by} and {filter_name}.{param_name} "  # type: ignore[attr-defined]
                    f"with different defaults ({clone.value_default!r} and {declared.value_default!r}): "
                    "one widget has one default, give both parameters the same default"
                )
            return clone

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
                declared_controls = Control.get_controls(filt_dict["function_object"])
                if id(filt_dict["function_object"]) not in seen_function_ids:
                    suffix = ""
                else:
                    # Repeated filter: each repeat gets its own clones, suffixed
                    # like the filter name ("amount" -> "amount_1"). Key/timer-bound
                    # controls are not cloned - their key bindings would collide -
                    # so repeats run those with default values.
                    suffix = f"_{filters_count[filt_dict['function_name']]}"
                    declared_controls = {
                        param_name: ctrl
                        for param_name, ctrl in declared_controls.items()
                        if not isinstance(ctrl, (KeyboardControl, TimeControl))
                    }
                registered_controls = {
                    param_name: pipeline_control(ctrl, suffix, filt_name, param_name)
                    for param_name, ctrl in declared_controls.items()
                }
                params_to_analyze = {**func_kwargs, **registered_controls}
            # Literal keyword arguments in the pipeline body (`amplify(img, gain=2.5)`)
            # set this instance's value; a bound control gets a per-instance clone
            # with that default so the other instances keep theirs.
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
            # the pipeline line calling this filter: output count checks and messages
            filt.call_location = filt_dict.get("location")
            filters.append(filt)
            filters_names.append(filt_name)
            seen_function_ids.add(id(filt_dict["function_object"]))
        logging.debug(filters_count)
        logging.debug(filters_names)

        bindings = cls._disambiguate_control_names(bindings)
        control_list = []
        connected = set()
        for filt, param_name, ctrl in bindings:
            if id(ctrl) in connected:
                ctrl._add_target(filt, param_name)  # one control shared by several filters
            else:
                ctrl.connect_filter(filt, param_name)
                connected.add(id(ctrl))
                control_list.append(ctrl)
            filt.values = {param_name: ctrl.value_default}

        # GUI widgets are keyed by control name: distinct controls sharing a
        # name within one pipeline would silently drive the wrong filter.
        controls_by_name = {}
        for ctrl in control_list:
            previous = controls_by_name.get(ctrl.name)
            if previous is not None and previous is not ctrl:
                where = ", ".join(f"{f.name}.{p}" for f, p in previous.targets + ctrl.targets)
                raise ValueError(
                    f"Duplicate control name '{ctrl.name}' in pipeline '{pipe.__name__}' ({where}): "
                    "two different controls cannot have the same name. "
                    "To drive several filters with one widget, declare the control once and pass the same object "
                    f"to each filter (band = Control(...); @interactive(band=band) on both); "
                    "otherwise pass a distinct name=... to one of them."
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

        A control shared by several filters (the same declared object) is
        never renamed. Renamed controls are clones: the declared control is
        never mutated, and building the same pipeline twice gives the same names.
        """
        uses: dict = {}
        for _filt, _param, ctrl in bindings:
            uses[id(ctrl)] = uses.get(id(ctrl), 0) + 1
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
                # a control shared by several filters keeps its name (it is one widget)
                if ctrl._auto_named and uses[id(ctrl)] == 1:
                    colliding_params.add(param_name)
        if not colliding_params:
            return bindings
        renamed = []
        for filt, param_name, ctrl in bindings:
            if ctrl._auto_named and uses[id(ctrl)] == 1 and param_name in colliding_params:
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

    def load_tuning(self, path: Path) -> None:
        """Load a json/yaml tuning file written by ``export_tuning`` (alias of ``import_tuning``).

        Example:
            ```python
            pipe.export_tuning("my_tuning.yaml")
            pipe.load_tuning("my_tuning.yaml")
            ```
        """
        self.import_tuning(path)

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
            for filt, param_name in ctrl.targets:
                current_params.setdefault(filt.name, {})[param_name] = ctrl.value
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
    ) -> List[Path]:
        """Run the pipeline and write its outputs (and the tuning) next to ``path``.

        Output ``name`` is written to ``<stem>_<name><suffix>``, the current
        parameters to ``<stem>.yaml``. The format follows the output type:

        - numpy image (``(H, W)``, ``(H, W, 1|3|4)``; float in ``[0, 1]``,
          uint8, uint16 or bool) -> image file through ``Image`` (``path``'s
          suffix if it is ``.png``/``.jpg``/``.tif``, else ``.png``)
        - 1D numpy array -> ``.csv``; any other numpy array -> ``.npy``
        - ``Image``, ``Curve``, ``SingleCurve``, ``Table`` -> their own ``save``
          (``path``'s suffix when they support it, else their default one)
        - ``str`` -> ``.txt``

        Other output types are skipped with a single warning. Pass
        ``data_wrapper_fn`` to wrap every output yourself (it must return an
        object with a ``save(path)`` method).

        Args:
            path: Base file path, e.g. ``"out/result.png"``.
            data_wrapper_fn: Optional wrapper applied to each output.
            output_indexes: Names (or indexes) of the buffers to save;
                defaults to the pipeline outputs.
            save_entire_buffer: Save every intermediate buffer.

        Returns:
            The list of written output files (the tuning file excluded).
        """
        if output_indexes is None:
            if self.outputs is not None:
                output_indexes = self.outputs
            else:
                output_indexes = self.filters[-1].outputs
        if save_entire_buffer:
            output_indexes = None  # you may force specific buffer index you'd like to save
        wanted = None if output_indexes is None else set(_flatten_outputs(output_indexes))
        result_full = super().run()
        if result_full is None:
            return []
        if path is None:
            raise ValueError("path must be provided for saving")
        if not isinstance(path, Path):
            path = Path(path)
        self.export_tuning(path.with_suffix(".yaml"))
        if not isinstance(result_full, dict):
            raise RuntimeError(f"Expected dict from pipeline run, got {type(result_full)}")
        written: List[Path] = []
        skipped = []
        for num, res_current in result_full.items():
            if wanted is not None and num not in wanted:
                continue
            if res_current is None or (isinstance(res_current, list) and len(res_current) == 0):
                continue
            current_name = path.with_name(f"{path.stem}_{_safe_file_part(num)}{path.suffix}")
            try:
                if data_wrapper_fn is not None:
                    to_save = data_wrapper_fn(res_current)
                    if not hasattr(to_save, "save"):
                        raise AttributeError(f"Result object {type(to_save)} has no 'save' method")
                    to_save.save(current_name)  # type: ignore
                    saved_path = getattr(to_save, "path", None) or current_name
                else:
                    saved_path = _save_output(res_current, current_name)
                    if saved_path is None:
                        skipped.append(f"{num} ({type(res_current).__name__})")
                        continue
            except Exception:
                # Broad on purpose: one failed output must not abort the
                # whole batch save; continue with the remaining outputs.
                logging.exception(f"Cannot save output {num} to {current_name}")
                continue
            written.append(Path(saved_path))
            logging.info(f"saved output {num} to {saved_path}")
        if skipped:
            logging.warning(
                f"Not saved (unsupported output type): {', '.join(skipped)}. "
                "Supported: numpy arrays, Image, Curve, SingleCurve, Table, str - "
                "or pass data_wrapper_fn=... returning an object with a save(path) method."
            )
        return written

    def parameters_from_keyword_args(self, **kwargs) -> dict:
        """Map ``pipeline(img, gain=2.0)`` keyword arguments to ``{filter: {param: value}}``.

        Same spellings as ``snapshot`` / ``sweep``: a parameter name sets it in
        every filter that has one, a control name (``exposure``, ``gain_1``,
        ``amplify.gain``) sets the parameter it drives, ``"filter.param"``
        (``pipe(img, **{"amplify.gain": 2.0})``) sets one filter only.

        Raises:
            TypeError: if a keyword matches no parameter.
        """
        from interactive_pipe.headless.explore import resolve_names

        resolved = resolve_names(
            self,
            list(kwargs),
            caller=f"pipeline '{self.name}'",
            reserved=("inputs", "parameters", "context"),
        )
        new_param_dict: dict = {}
        for key, value in kwargs.items():
            for filter_name, param_name in resolved[key]:
                new_param_dict.setdefault(filter_name, {})[param_name] = value
        return new_param_dict

    def __call__(self, *inputs_tuple, inputs=None, parameters=None, context=None, **kwargs) -> Any:
        # validated first: an unknown keyword raises before anything is changed
        kwargs_params = self.parameters_from_keyword_args(**kwargs)
        if parameters is not None:
            from interactive_pipe.headless.explore import check_parameters_dict

            check_parameters_dict(self, parameters, f"pipeline '{self.name}'")
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

    # See-the-result loop: render runs to PNG files (interactive_pipe.headless.explore)
    from interactive_pipe.headless.describe import describe, summary
    from interactive_pipe.headless.explore import snapshot, sweep
