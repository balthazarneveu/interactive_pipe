import logging
import sys
import time
import traceback
from copy import deepcopy


class PipelineEngine:
    def __init__(self, cache=False, safe_input_buffer_deepcopy=False) -> None:
        self.cache = cache
        self.safe_input_buffer_deepcopy = safe_input_buffer_deepcopy

    def run(self, filters, imglst=None):
        performances = []
        logging.debug(100 * "-")
        if self.safe_input_buffer_deepcopy:
            # Want to be safe when there's no cache? always keep the input buffers of the first filter untouched
            logging.debug(f"<<< Deepcopy input images ")
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
            # 1     | 0           | True -> cache with no change, skip the calculation
            # 1     | 1           | False -> cache and result changed, cannot skip so calculate
            skip_calculation &= (prc.cache_mem is not None) and (not prc.cache_mem.has_changed(prc.values))

            if skip_calculation and self.cache:
                logging.debug(
                    f"-->  Load cached outputs from filter {idx}: {prc.name}")
                out = prc.cache_mem.result
                previous_calculation = False
            else:
                logging.debug(
                    ("... " if previous_calculation else "!!! ") + f"Calculating {prc.name}")
                try:
                    if prc.inputs is None:
                        out = prc.apply(prc.values)
                    else:
                        out = prc.apply(
                            *[result[idi] if idi is not None else None for idi in prc.inputs] + prc.values)
                except Exception as e:
                    logging.error(f'Error in {prc.name} filter:')
                    logging.error(e)
                    traceback.print_exc()
                    sys.exit(1)
                previous_calculation = True
                if self.cache and prc.cache_mem is not None:  # cache result if cache available
                    logging.debug(f"<-- Storing result from {prc.name}")
                    prc.cache_mem.update(out)

            # put prc output at the right position within result vector
            if prc.outputs is not None:
                for i, ido in enumerate(prc.outputs):
                    if ido >= len(result):
                        for j in range(0, ido - len(result) + 1):
                            result.append([])
                    if isinstance(out, list):
                        result[ido] = out[i]
                    # Simpler manner of defining a process fuction (do not return a list)
                    else:
                        result[ido] = out
            toc = time.perf_counter()
            performances.append(f"{prc.name}: {toc - tic:0.4f} seconds")

        # Limit result using self.numfigs but with indices pointed by last filter
        logging.info("\n".join(performances))
        return result
