import inspect
from typing import Any, Callable, Dict, List, Tuple


def analyze_apply_fn_signature(apply_fn: Callable) -> Tuple[List[str], Dict[str, Any]]:
    signature = inspect.signature(apply_fn)
    keyword_args = {k: v.default for k, v in signature.parameters.items() if v.default is not inspect.Parameter.empty}

    positional_args = [k for k, v in signature.parameters.items() if v.default is inspect.Parameter.empty]
    return positional_args, keyword_args
