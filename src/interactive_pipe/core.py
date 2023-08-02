import logging
import sys
import time
import traceback
from copy import deepcopy
from typing import Dict, List, Optional, Callable, Tuple
from sliders import Slider
import inspect
from cache import CachedResults

"""
:param apply_fn: Callable
    ```
    def apply_fn(*imgs, global_context={}, **params) -> list:
    '''
    :param global_context: dictionary containing global context
    :param imgs: img0, img1, img2 ...
    - (img0, ... are the results from the previous step)

    :param kwargs: value1 = ... , value2 = ..., value3 = ...
        - dictionary containing all parameters
        - follow the parameters to be applied  `self.values`
    :return: output1, output2 ...

    ```
:param name: optional, if None, using the apply_fn name (or finally the class Name)
"""

"""
You can implement your own apply method if you need complex class usage 
otherwise, just use the `apply_fn`.
```
    def apply(self, *imgs, **kwargs) -> list:
    '''
    :param imgs: img0, img1, img2 ...
        - (img0, ... are the results from the previous step)
        - indexes of images processed is defined by `self.inputs`
        - indexes of output images to be processed are defined by `self.outputs`

    :param kwargs: value1 = ... , value2 = ..., value3 = ...
        - dictionary containing all parameters
        - follow the parameters to be applied  `self.values`
    :return: output1, output2 ...
    '''
        raise NotImplementedError("Need to implement the apply method")

```
"""
# TODO: fix docstring PureFilter

# TODO: harmonization of default_params & values naming
# TODO: harmonization of global_params as context


class PureFilter:
    def __init__(self, apply_fn: Optional[Callable] = None, name: Optional[str] = None, default_params: dict = {}, global_params: dict = {}):
        self.name = name if name else (
            self.__class__.__name__ if not apply_fn else apply_fn.__name__)
        self.values = deepcopy(default_params)
        if apply_fn is not None:
            self.apply = apply_fn
        self.set_global_params(global_params)

    def set_global_params(self, global_params: dict):
        self.global_params = global_params

    def check_apply_signature(self):
        if not hasattr(self, "__args_names") or not hasattr(self, "__kwargs_names"):
            self.__args_names, self.__kwargs_names = self.analyze_apply_fn_signature(
                self.apply)
        else:  # skip computing signature
            pass

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, new_values):
        assert isinstance(
            new_values, dict), f"{new_values} is not a dictionary"
        self._values = new_values

    def run(self, *imgs) -> list:
        # First we check if the keyword args of the apply function match with self.values
        assert isinstance(self.values, dict), f"{self.values}"
        self.check_apply_signature()
        for key, val in self.values.items():
            assert key in self.__kwargs_names.keys(
            ), f"{key} not in {self.__kwargs_names.keys()}"
        if "global_params" in self.__kwargs_names.keys():
            # special key to provide the context dictionary
            out = self.apply(
                *imgs, global_params=self.global_params, **self.values)
        else:
            out = self.apply(*imgs, **self.values)
        return out

    @staticmethod
    def analyze_apply_fn_signature(apply_fn: Callable) -> Tuple[dict, dict]:
        signature = inspect.signature(apply_fn)
        keyword_args = {
            k: v.default
            for k, v in signature.parameters.items()
            if v.default is not inspect.Parameter.empty
        }

        positional_args = [
            k
            for k, v in signature.parameters.items()
            if v.default is inspect.Parameter.empty
        ]
        return positional_args, keyword_args


class FilterCore(PureFilter):
    """PureFilter + cache + routing nodes defined (inputs & outputs fields)"""

    def __init__(self,
                 apply_fn: Callable = None,
                 name: Optional[str] = None,
                 default_params: dict = {},
                 global_params: dict = {},
                 inputs: List[int] = [0],
                 outputs: List[int] = [0],
                 cache=True,
                 ):
        super().__init__(apply_fn=apply_fn, name=name,
                         default_params=default_params, global_params=global_params)
        self.inputs = inputs
        self.outputs = outputs
        self.cache = cache
        self.reset_cache()

    def reset_cache(self):
        if self.cache:
            self.cache_mem = CachedResults(self.name)
        else:
            self.cache_mem = None

    def run(self, *imgs) -> list:
        # TODO: support routing mechanism based on List[int] or List[str | generic routing object]
        assert len(imgs) == len(
            self.inputs), "number of inputs shall match what's expected"
        if self.inputs is None:
            filter_in = ()
        else:
            filter_in = imgs
        out = super().run(*filter_in)
        if out is not None:
            assert len(out) >= len(
                self.outputs), "number of outputs shall be at least greater or equal to what's expected by the filter"
        assert isinstance(out, list)
        return out

    def __repr__(self) -> str:
        descr = "%s\n" % self.name
        if not (self.inputs == [0] and self.outputs == [0]):
            descr += "(" + (",".join(["%d" % it for it in self.inputs])) + ")"
            descr += "->" + \
                "(" + ",".join(["%d" % it for it in self.outputs]) + ")\n"
        descr += "\n"
        return descr


class PipelineEngine:
    def __init__(self, cache=False, safe_input_buffer_deepcopy=True) -> None:
        self.cache = cache
        self.safe_input_buffer_deepcopy = safe_input_buffer_deepcopy

    def run(self, filters: List[FilterCore], imglst=None):
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
            skip_calculation &= (prc.cache_mem is not None) and (
                not prc.cache_mem.has_changed(prc.values))

            if skip_calculation and self.cache:
                logging.debug(
                    f"-->  Load cached outputs from filter {idx}: {prc.name}")
                out = prc.cache_mem.result
                previous_calculation = False
            else:
                logging.debug(
                    ("... " if previous_calculation else "!!! ") + f"Calculating {prc.name}")
                try:
                    routing_in = []
                    if prc.inputs:
                        routing_in = [
                            result[idi] if idi is not None else None for idi in prc.inputs]
                    out = prc.run(*routing_in)
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

# TODO: write tests and execution samples.


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
