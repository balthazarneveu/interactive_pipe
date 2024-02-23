import ast
import inspect
import logging
from typing import List, Callable, Tuple, Optional, Union
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.signature import analyze_apply_fn_signature


def get_name(node: ast.NodeVisitor) -> Union[str, List[str], None]:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        return [get_name(elt) for elt in node.elts]
    else:
        return None


def flatten_target_names(targets: List[Union[list, str, None]], mapping_function: Optional[Callable] = None) -> List[str]:
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


def get_call_graph(func: Callable, global_context=None) -> dict:
    code = inspect.getsource(func)
    tree = ast.parse(code)
    results = []
    if global_context is None:
        module = inspect.getmodule(func)
        global_context = module.__dict__
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            function_name = get_name(node.value.func)
            input_names = [get_name(arg) for arg in node.value.args]
            results.append({
                "function_name": function_name,
                "function_object": global_context[function_name],
                "args": input_names,
                "returns": [],
                "output_names": [],
            })
            logging.debug(f"Function without assignment {function_name}")
        elif isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
            if isinstance(value, ast.Call):
                function_name = get_name(value.func)
                logging.debug(
                    f"classic function with assignment {function_name}")
                assert function_name in global_context.keys(
                ), f"Probably mispelled {function_name}"
                input_names = [get_name(arg) for arg in value.args]
                output_names = flatten_target_names(
                    targets, mapping_function=get_name)
                function_object = global_context[function_name]
                if isinstance(function_object, FilterCore):
                    # Case of a filter instance
                    function_object.check_apply_signature()
                    # ---> forcing filter instance .name to be the name of the object used in the func
                    function_object.name = function_name
                    # you could use instead: # function_name = function_object.name to keep the original name
                    sig = function_object.signature
                    function_object.inputs = input_names
                    function_object.outputs = output_names
                    function_apply = function_object
                elif isinstance(function_object, Callable):
                    # Case of a decorated function
                    sig = analyze_apply_fn_signature(function_object)
                    function_apply = global_context[function_name]
                else:
                    raise TypeError(
                        f"Not supported {function_name} - should be function or FilterCore")
                results.append({
                    "function_name": function_name,
                    "function_object": function_apply,
                    "signature": {"args": sig[0], "kwargs": sig[1]},
                    "args": input_names,
                    "returns": output_names,
                })
    main_function = tree.body[0]
    outputs = [get_name(ret.value)
               for ret in main_function.body if isinstance(ret, ast.Return)]
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
