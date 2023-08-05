import ast
import inspect
from typing import List, Callable, Tuple, Optional

def get_name(node: ast.NodeVisitor) -> str|List[str]|None:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        return [get_name(elt) for elt in node.elts]
    else:
        return None
    
def flatten_target_names(targets: List[list|str|None], mapping_function: Optional[Callable]=None) -> List[str]:
    output_names = []
    for target in targets:
        target_name = mapping_function(target) if mapping_function else target
        if target_name:
            if isinstance(target_name, str):
                output_names.append(target_name)
            else:
                output_names.extend(target_name)
    if len(output_names) == 0:
        return None
    return output_names


def get_call_graph(func:Callable, global_context=None) -> dict:
    code = inspect.getsource(func)
    tree = ast.parse(code)
    results = []
    if global_context is None:
        module = inspect.getmodule(func)
        global_context = module.__dict__
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
            if isinstance(value, ast.Call):
                function_name = get_name(value.func)
                assert function_name in global_context.keys()
                input_names = [get_name(arg) for arg in value.args]
                output_names = flatten_target_names(targets, mapping_function=get_name)
                function_object = global_context[function_name]
                sig = analyze_apply_fn_signature(function_object)
                results.append({
                    "function_name": function_name,
                    "function_object": global_context[function_name],
                    "signature" : {"args": sig[0], "kwargs": sig[1]},
                    "args": input_names,
                    "returns": output_names,
                })
    main_function = tree.body[0]
    outputs = [get_name(ret.value)  for ret in main_function.body if isinstance(ret, ast.Return)]
    assert len(outputs) <= 1, "cannot return several times!"
    outputs = flatten_target_names(outputs, mapping_function=None)
    inputs, kwargs = analyze_apply_fn_signature(func)
    graph = {
        "function_name": main_function.name,
        "call_graph": results,
        "args": inputs,
        "kwargs": kwargs,
        "returns": outputs
    }

    return graph

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