import inspect
from typing import Callable, Tuple


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
