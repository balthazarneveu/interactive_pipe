import ast
import inspect
import logging
from typing import Any, Callable, List, Optional, Sequence, Union

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.signature import analyze_apply_fn_signature


def get_name(node, preserve_structure=False) -> Union[str, Sequence[Any], None]:  # type: ignore
    """Extract name from AST node. Accepts ast.expr nodes.

    Args:
        node: AST node to extract name from
        preserve_structure: If True, preserve nested list/tuple structure; if False, flatten
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        names = [get_name(elt, preserve_structure=preserve_structure) for elt in node.elts]
        if preserve_structure:
            # Preserve nested structure - filter out None but keep nesting
            return [name for name in names if name is not None] or None
        else:
            # Flatten nested lists and filter out None values (original behavior)
            result = []
            for name in names:
                if name is not None:
                    if isinstance(name, list):
                        result.extend(name)
                    else:
                        result.append(name)
            return result if result else None
    else:
        return None


def flatten_target_names(
    targets,
    mapping_function: Optional[Callable] = None,  # type: ignore
) -> Optional[List[str]]:
    """Flatten list of targets (which may be AST nodes or already processed names)."""
    output_names = []
    for target in targets:
        target_name = mapping_function(target) if mapping_function else target
        if target_name:
            if isinstance(target_name, str):
                output_names.append(target_name)
            elif isinstance(target_name, list):
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
            if function_name is None or function_name not in global_context:
                raise KeyError(f"Function name '{function_name}' not found in global context")
            if not isinstance(function_name, str):
                raise TypeError(f"Function name must be a string, got {type(function_name)}")
            input_names = [get_name(arg) for arg in node.value.args]
            results.append(
                {
                    "function_name": function_name,
                    "function_object": global_context[function_name],
                    "args": input_names,
                    "returns": [],
                    "output_names": [],
                }
            )
            logging.debug(f"Function without assignment {function_name}")
        elif isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
            if isinstance(value, ast.Call):
                function_name = get_name(value.func)
                logging.debug(f"classic function with assignment {function_name}")
                if function_name is None or function_name not in global_context:
                    raise KeyError(
                        f"Function name '{function_name}' not found in global context. "
                        f"Probably misspelled {function_name}"
                    )
                input_names = [get_name(arg) for arg in value.args]
                output_names = flatten_target_names(targets, mapping_function=get_name)  # type: ignore
                if not isinstance(function_name, str):
                    raise TypeError(f"Function name must be a string, got {type(function_name)}")
                function_object = global_context[function_name]
                if isinstance(function_object, FilterCore):
                    # Case of a filter instance
                    function_object.check_apply_signature()
                    # ---> forcing filter instance .name to be the name of the object used in the func
                    if isinstance(function_name, str):
                        function_object.name = function_name
                    # you could use instead: # function_name = function_object.name to keep the original name
                    sig = function_object.signature
                    function_object.inputs = input_names  # type: ignore
                    function_object.outputs = output_names  # type: ignore
                    function_apply = function_object
                elif isinstance(function_object, Callable):
                    # Case of a decorated function
                    sig = analyze_apply_fn_signature(function_object)
                    if isinstance(function_name, str):
                        function_apply = global_context[function_name]
                    else:
                        function_apply = function_object
                else:
                    raise TypeError(f"Not supported {function_name} - should be function or FilterCore")
                results.append(
                    {
                        "function_name": function_name,
                        "function_object": function_apply,
                        "signature": {"args": sig[0], "kwargs": sig[1]},
                        "args": input_names,
                        "returns": output_names,
                    }
                )
    if not tree.body:
        raise ValueError("Function body is empty")
    main_function = tree.body[0]
    if not isinstance(main_function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError("Function AST node is malformed")
    # Get return statements and preserve nested structure
    return_nodes = [ret.value for ret in main_function.body if isinstance(ret, ast.Return)]
    assert len(return_nodes) <= 1, "cannot return several times!"

    if return_nodes:
        # Check if the return value is a nested list/tuple structure
        ret_node = return_nodes[0]
        if isinstance(ret_node, (ast.List, ast.Tuple)):
            # Check if any element is itself a list/tuple (indicating 2D structure)
            has_nested_structure = any(isinstance(elt, (ast.List, ast.Tuple)) for elt in ret_node.elts)
            if has_nested_structure:
                # Preserve the nested structure for 2D output layouts
                outputs = get_name(ret_node, preserve_structure=True)
            else:
                # Flatten for simple 1D lists/tuples (original behavior)
                outputs = flatten_target_names([get_name(ret_node, preserve_structure=False)], mapping_function=None)
        else:
            # Single return value or name
            outputs = flatten_target_names([get_name(ret_node, preserve_structure=False)], mapping_function=None)
    else:
        outputs = None
    inputs, kwargs = analyze_apply_fn_signature(func)
    graph = {
        "function_name": main_function.name,
        "call_graph": results,
        "args": inputs,
        "kwargs": kwargs,
        "returns": outputs,
    }

    return graph
