import logging
import os
import sys
import time
import traceback
from copy import deepcopy
from typing import List
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
        print(f"\n{'='*60}", file=file)
        print("PIPELINE ERROR", file=file)
        print(f"{'='*60}", file=file)
        print(str(self), file=file)
        print(f"{'='*60}\n", file=file)


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


class PipelineEngine:
    def __init__(self, cache=False, safe_input_buffer_deepcopy=True) -> None:
        self.cache = cache
        self.safe_input_buffer_deepcopy = safe_input_buffer_deepcopy

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

        skip_calculation = True
        previous_calculation = False
        for idx, prc in enumerate(filters):
            tic = time.perf_counter()
            # if cache not available or if cache available and values have changed, need to recalculate from now on
            # cache | has changed | skip_calculation
            # 0     | X           | False -> no cache, cannot skip so calculate
            # 1     | 0           | True  -> cache with no change, skip the calculation
            # 1     | 1           | False -> cache and result changed, cannot skip so calculate
            skip_calculation &= (prc.cache_mem is not None) and (
                not prc.cache_mem.has_changed(prc.values)
            )

            if skip_calculation and self.cache:
                logging.debug(f"-->  Load cached outputs from filter {idx}: {prc.name}")
                out = prc.cache_mem.result
                previous_calculation = False
            else:
                logging.debug(
                    ("... " if previous_calculation else "!!! ")
                    + f"Calculating {prc.name}"
                )
                try:
                    routing_in = []
                    if prc.inputs:
                        routing_in = [
                            result[idi] if idi is not None else None
                            for idi in prc.inputs
                        ]
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
                previous_calculation = True
                if (
                    self.cache and prc.cache_mem is not None
                ):  # cache result if cache available
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

        # Limit result using self.numfigs but with indices pointed by last filter
        logging.info("\n".join(performances))
        logging.info(f"Full buffer: {len(result)}")
        return result
