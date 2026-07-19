import logging
import os
import sys
import time
import traceback
from copy import deepcopy
from typing import List, Optional, Set, Union

from interactive_pipe.core.context_tracking import GRAPH_CACHE_MODES, ContextTracker
from interactive_pipe.core.filter import FilterCore


class FilterError(Exception):
    """Clean, user-friendly exception for filter errors.

    Displays only the relevant error information without the full
    framework traceback, making it easier to identify issues in user code.
    """

    def __init__(self, filter_name: str, original_error: Exception, tb=None):
        self.filter_name = filter_name
        self.original_error = original_error
        self.tb = tb
        self._user_frames = self._extract_user_frames()
        super().__init__(self._format_message())

    def _extract_user_frames(self):
        """Extract relevant frames from the traceback (user code, not framework)."""
        if self.tb is None:
            return []

        # Walk through traceback to find the user's code (not in interactive_pipe/src)
        tb_list = traceback.extract_tb(self.tb)
        user_frames = []
        for frame in tb_list:
            # Skip frames from the interactive_pipe framework itself
            if "interactive_pipe" in frame.filename and "/src/" in frame.filename:
                continue
            user_frames.append(frame)

        # If no user frames found, return last frame from traceback
        if not user_frames and tb_list:
            return [tb_list[-1]]
        return user_frames

    def _format_message(self):
        """Format a clean, readable error message."""
        error_str = str(self.original_error)

        lines = [
            "",
            f"  Filter '{self.filter_name}' raised {type(self.original_error).__name__}:",
            f"    {error_str}",
        ]

        if self._user_frames:
            lines.append("")
            lines.append("  Traceback (user code only):")
            for frame in self._user_frames:
                lines.append(f"    {frame.filename}:{frame.lineno} in {frame.name}()")
                if frame.line:
                    lines.append(f"      >>> {frame.line.strip()}")

        lines.append("")
        return "\n".join(lines)

    def print_compact(self, file=None):
        """Print a compact version of the error to stderr or specified file."""
        if file is None:
            file = sys.stderr
        print(f"\n{'=' * 60}", file=file)
        print("PIPELINE ERROR", file=file)
        print(f"{'=' * 60}", file=file)
        print(str(self), file=file)
        print(f"{'=' * 60}\n", file=file)


# Install a custom exception hook to handle FilterError cleanly
_original_excepthook = sys.excepthook


def _filter_error_excepthook(exc_type, exc_value, exc_tb):
    """Custom exception hook that handles FilterError without full traceback."""
    if exc_type is FilterError:
        # FilterError already printed its compact form, just show a hint
        print("Hint: Set INTERACTIVE_PIPE_DEBUG=1 for full traceback", file=sys.stderr)
        if os.environ.get("INTERACTIVE_PIPE_DEBUG"):
            _original_excepthook(exc_type, exc_value, exc_tb)
    else:
        _original_excepthook(exc_type, exc_value, exc_tb)


sys.excepthook = _filter_error_excepthook


def _readonly_view(value):
    """Return numpy arrays as read-only views (recursing into lists/tuples of buffers).

    Views copy nothing: mutating the returned object raises a ValueError at the
    offending line, while reading is untouched. Non-numpy values pass through
    unprotected (no cheap read-only wrapper exists for them).
    """
    value_type = type(value)
    if value_type.__module__ == "numpy" and value_type.__name__ == "ndarray":
        view = value.view()
        view.flags.writeable = False
        return view
    if isinstance(value, (list, tuple)):
        return type(value)(_readonly_view(item) for item in value)
    return value


def _build_dependency_indexes(filters: List[FilterCore]) -> List[Set[int]]:
    """For each filter, the indexes of upstream filters producing its inputs.

    Source order is always a valid topological order (a variable is produced before
    it is consumed), so dependencies only point backwards in the filter list.
    """
    producer = {}  # variable name (or index) -> index of the filter producing it
    dependencies: List[Set[int]] = []
    for idx, prc in enumerate(filters):
        deps = set()
        for inp in prc.inputs or []:
            if inp is not None and inp in producer:
                deps.add(producer[inp])
        dependencies.append(deps)
        for out in prc.outputs or []:
            producer[out] = idx
    return dependencies


class PipelineEngine:
    """Executes a list of filters sequentially, with three cache modes:

    - cache=False: recompute every filter on every run.
    - cache=True: sequential prefix cache. A filter is skipped only when its own
      parameters AND those of every filter before it (in list order) are unchanged.
    - cache="graph": dependency-aware cache. A filter is recomputed only when its own
      parameters changed, one of its actual producers (variable routing) was recomputed,
      or a context key it reads was updated (tracked at runtime through a ContextTracker).
      Filters using legacy context injection (global_params & aliases) act as barriers:
      they are recomputed whenever any earlier filter is recomputed.
    - cache="graph-strict": same as "graph", but context reads return numpy arrays as
      read-only views so accidental in-place mutation raises at the offending line.

    Filter inputs are handed out as read-only numpy views by default (readonly_inputs=True):
    mutating an input in place (img += 1) raises at the offending line instead of silently
    corrupting sibling filters or cached buffers. Filters declaring inplace=True receive
    private writable deep copies of their inputs instead.
    """

    def __init__(
        self,
        cache: Union[bool, str] = False,
        safe_input_buffer_deepcopy=True,
        readonly_inputs: bool = True,
    ) -> None:
        self.cache = cache
        self.safe_input_buffer_deepcopy = safe_input_buffer_deepcopy
        self.readonly_inputs = readonly_inputs
        # trackers wired by PipelineCore when cache == "graph":
        # - context_tracker wraps the user context (new `context` proxy API)
        # - global_params_tracker wraps the legacy shared dict (global_params injection
        #   and class filters accessing self.global_params)
        self.context_tracker: Optional[ContextTracker] = None
        self.global_params_tracker: Optional[ContextTracker] = None

    def run(self, filters: List[FilterCore], imglst=None):
        performances = []
        logging.debug(100 * "-")
        result = {}
        if imglst is not None:
            if isinstance(imglst, list):
                for input_index, inp in enumerate(imglst):
                    if self.safe_input_buffer_deepcopy:
                        result[input_index] = deepcopy(inp)
                        logging.debug(f"<<< Deepcopy input images {input_index}")
                    else:
                        result[input_index] = inp
            elif isinstance(imglst, dict):
                if self.safe_input_buffer_deepcopy:
                    logging.debug("<<< Deepcopy input images")
                    result = deepcopy(imglst)
                else:
                    result = imglst

        graph_mode = self.cache in GRAPH_CACHE_MODES
        trackers: List[ContextTracker] = []
        if graph_mode:
            trackers = [t for t in (self.context_tracker, self.global_params_tracker) if t is not None]
        dependencies = _build_dependency_indexes(filters) if graph_mode else []
        dirty_flags: List[bool] = []
        # per tracker: context keys updated outside of the pipeline run (GUI events,
        # user code) - either through tracked writes or silent in-place mutation
        changed_keys: dict = {id(t): set(t.consume_external_changes()) | t.detect_silent_changes() for t in trackers}
        run_writes: List[tuple] = []  # (filter index, tracker, context keys changed this run)

        skip_calculation = True
        previous_calculation = False
        for idx, prc in enumerate(filters):
            tic = time.perf_counter()
            if graph_mode:
                # dependency-aware cache: a filter is dirty when its own parameters changed,
                # one of its producers is dirty, or a context key it reads was updated
                params_changed = (prc.cache_mem is None) or prc.cache_mem.has_changed(prc.values)
                deps_dirty = any(dirty_flags[dep] for dep in dependencies[idx])
                if prc.uses_legacy_context and self.global_params_tracker is None:
                    # legacy shared dict untracked (engine used standalone without a
                    # PipelineCore wiring the trackers): conservative barrier
                    deps_dirty = deps_dirty or any(dirty_flags)
                context_dirty = any(t.reads_changed_keys(prc.name, changed_keys[id(t)]) for t in trackers)
                is_dirty = params_changed or deps_dirty or context_dirty
                dirty_flags.append(is_dirty)
                skip_calculation = not is_dirty
            else:
                # if cache not available or if cache available and values have changed,
                # need to recalculate from now on
                # cache | has changed | skip_calculation
                # 0     | X           | False -> no cache, cannot skip so calculate
                # 1     | 0           | True  -> cache with no change, skip the calculation
                # 1     | 1           | False -> cache and result changed, cannot skip so calculate
                skip_calculation &= (prc.cache_mem is not None) and (not prc.cache_mem.has_changed(prc.values))

            if skip_calculation and self.cache:
                logging.debug(f"-->  Load cached outputs from filter {idx}: {prc.name}")
                if prc.cache_mem is None:
                    raise RuntimeError(f"Cache memory is None for filter {prc.name}")
                out = prc.cache_mem.result
                previous_calculation = False
            else:
                logging.debug(("... " if previous_calculation else "!!! ") + f"Calculating {prc.name}")
                for trk in trackers:
                    # attribute context reads/writes to this filter while it runs
                    trk.begin_filter(prc.name)
                try:
                    routing_in = []
                    if prc.inputs:
                        routing_in = [result[idi] if idi is not None else None for idi in prc.inputs]
                    if self.readonly_inputs and routing_in:
                        if getattr(prc, "inplace", False):
                            # declared in-place filter: private writable copies keep the
                            # shared buffers and upstream caches safe
                            routing_in = [deepcopy(buf) for buf in routing_in]
                        else:
                            # read-only views: in-place mutation raises at the user's line
                            routing_in = [_readonly_view(buf) for buf in routing_in]
                    logging.debug(f"in types-> {[type(inp) for inp in routing_in]}")
                    out = prc.run(*routing_in)
                    if out is not None:
                        try:
                            logging.debug(f"out types-> {[type(ou) for ou in out]}")
                        except TypeError:
                            # out is not iterable (e.g., single value)
                            logging.debug(f"out type-> {type(out)}")
                except Exception as e:
                    # Create a clean, user-friendly error
                    _, _, tb = sys.exc_info()
                    filter_error = FilterError(prc.name, e, tb)
                    filter_error.print_compact()
                    raise filter_error from None  # 'from None' suppresses the chained traceback
                finally:
                    filter_changes = [(trk, trk.finish_filter()) for trk in trackers]
                for trk, keys_changed in filter_changes:
                    if keys_changed:
                        # context keys updated by this filter dirty their readers downstream
                        changed_keys[id(trk)] |= keys_changed
                        run_writes.append((idx, trk, keys_changed))
                previous_calculation = True
                if self.cache and prc.cache_mem is not None:  # cache result if cache available
                    logging.debug(f"<-- Storing result from {prc.name}")
                    prc.cache_mem.update(out)
            # put prc output at the right position within result vector
            if prc.outputs is not None:
                for i, ido in enumerate(prc.outputs):
                    if isinstance(out, list) or isinstance(out, tuple):
                        result[ido] = out[i]
                    # Simpler manner of defining a process fuction (do not return a list)
                    else:
                        result[ido] = out
            toc = time.perf_counter()
            performances.append(f"{prc.name}: {toc - tic:0.4f} seconds")

        if run_writes:
            # Backward context edges (feedback across runs): when a filter updates a key
            # read by a filter located earlier in the pipeline (or by itself), the reader
            # computed with the previous value - invalidate its cache for the next run.
            # Readers located after the writer already saw the fresh value this run.
            name_to_idx = {filt.name: filt_idx for filt_idx, filt in enumerate(filters)}
            for writer_idx, trk, keys in run_writes:
                for key in keys:
                    for reader_name in trk.readers_of(key):
                        reader_idx = name_to_idx.get(reader_name)
                        if reader_idx is None or reader_idx > writer_idx:
                            continue
                        reader_cache = filters[reader_idx].cache_mem
                        if reader_cache is not None:
                            logging.debug(
                                f"Context feedback: {filters[writer_idx].name} updated '{key}', "
                                f"invalidating earlier reader {reader_name} for next run"
                            )
                            reader_cache.force_change = True

        # Limit result using self.numfigs but with indices pointed by last filter
        logging.info("\n".join(performances))
        logging.info(f"Full buffer: {len(result)}")
        return result
