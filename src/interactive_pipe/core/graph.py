"""Static analysis of a pipeline function into an execution graph.

The body of a pipeline function is never executed: it is parsed with ``ast``
and every top-level statement is turned into a node of the graph. Only a
small subset of Python can be expressed this way, so every statement is
validated and anything else raises a ``PipelineSyntaxError`` pointing at the
offending line, instead of being silently dropped.
"""

import ast
import builtins
import difflib
import inspect
import logging
import textwrap
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.signature import analyze_apply_fn_signature

ACCEPTED_SYNTAX = (
    "A pipeline body may only contain: a docstring, `pass`, filter calls "
    "(`out = flt(img)`, `a, b = flt(img)`, `flt(img)`, nested `blur(amplify(img))`, "
    "literal keyword arguments `amplify(img, gain=2.0)`) and one final `return`."
)


class PipelineSyntaxError(ValueError):
    """A pipeline function contains a statement the static graph analysis cannot express.

    Raised when the pipeline is built (decoration time). The message names the
    pipeline, the file and line, the offending source line and a hint on how to
    rewrite it. Subclass of ``ValueError`` so existing ``except ValueError``
    code keeps working.

    Attributes:
        pipeline_name: Name of the pipeline function.
        filename: Source file of the pipeline function.
        lineno: Absolute line number of the offending statement in ``filename``.
        source_line: The offending source line.
        hint: Suggested fix.
    """

    def __init__(
        self,
        message: str,
        pipeline_name: Optional[str] = None,
        filename: Optional[str] = None,
        lineno: Optional[int] = None,
        source_line: Optional[str] = None,
        hint: Optional[str] = None,
    ):
        self.pipeline_name = pipeline_name
        self.filename = filename
        self.lineno = lineno
        self.source_line = source_line
        self.hint = hint
        self.reason = message
        location = f"pipeline '{pipeline_name}'" if pipeline_name else "pipeline"
        if filename is not None:
            location += f", {filename}"
            if lineno is not None:
                location += f", line {lineno}"
        full_message = f"{location}: {message}"
        if source_line:
            full_message += f"\n    {source_line.strip()}"
        if hint:
            full_message += f"\nHint: {hint}"
        super().__init__(full_message)


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
    elif isinstance(node, (ast.Tuple, ast.List)):
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


_FILTER_HINT = (
    "wrap it in a filter function, e.g. `def scale(img): return img * 2` at module level, "
    "then `out = scale(img)` in the pipeline"
)
_CONDITION_HINT = (
    "move the condition inside a filter: give the filter a control (e.g. `@interactive(enabled=(True,))`) "
    "and branch in the filter body"
)
_LOOP_HINT = "loops cannot be expressed in the static graph: loop inside a filter, or write one filter call per step"

# (description, hint) for statements that are never allowed in a pipeline body
_STATEMENT_ERRORS: Dict[type, Tuple[str, str]] = {
    ast.If: ("`if` statements are not supported in a pipeline function", _CONDITION_HINT),
    ast.For: ("`for` loops are not supported in a pipeline function", _LOOP_HINT),
    ast.AsyncFor: ("`for` loops are not supported in a pipeline function", _LOOP_HINT),
    ast.While: ("`while` loops are not supported in a pipeline function", _LOOP_HINT),
    ast.With: (
        "`with` blocks are not supported in a pipeline function",
        "open the resource inside a filter, or outside the pipeline and pass the data as an input",
    ),
    ast.AsyncWith: (
        "`with` blocks are not supported in a pipeline function",
        "open the resource inside a filter, or outside the pipeline and pass the data as an input",
    ),
    ast.Try: (
        "`try` blocks are not supported in a pipeline function",
        "handle the exception inside the filter that may raise it",
    ),
    ast.AugAssign: (
        "augmented assignment (`+=`, `*=`, ...) is not supported in a pipeline function",
        f"assign a filter result to a name instead, e.g. `img = brighten(img)`; {_FILTER_HINT}",
    ),
    ast.FunctionDef: (
        "nested function definitions are not supported in a pipeline function",
        "define the filter next to the pipeline function (module level or the enclosing function)",
    ),
    ast.AsyncFunctionDef: (
        "nested function definitions are not supported in a pipeline function",
        "define the filter next to the pipeline function (module level or the enclosing function)",
    ),
    ast.ClassDef: (
        "class definitions are not supported in a pipeline function",
        "define the class outside the pipeline function",
    ),
    ast.Import: ("imports are not supported in a pipeline function", "import at module level"),
    ast.ImportFrom: ("imports are not supported in a pipeline function", "import at module level"),
    ast.Delete: ("`del` is not supported in a pipeline function", "simply stop using the variable"),
    ast.Assert: (
        "`assert` is not supported in a pipeline function",
        "check the condition inside a filter and raise there",
    ),
    ast.Raise: ("`raise` is not supported in a pipeline function", "raise from inside a filter"),
    ast.Global: ("`global` is not supported in a pipeline function", "share data with `context['key']`"),
    ast.Nonlocal: ("`nonlocal` is not supported in a pipeline function", "share data with `context['key']`"),
}
if hasattr(ast, "TryStar"):  # Python >= 3.11
    _STATEMENT_ERRORS[ast.TryStar] = _STATEMENT_ERRORS[ast.Try]  # type: ignore[attr-defined]
if hasattr(ast, "Match"):  # Python >= 3.10
    _STATEMENT_ERRORS[ast.Match] = ("`match` statements are not supported in a pipeline function", _CONDITION_HINT)  # type: ignore[attr-defined]

# (description, hint) for expressions found where a filter call is expected
_EXPRESSION_ERRORS: Dict[type, Tuple[str, str]] = {
    ast.BinOp: ("arithmetic is not supported in a pipeline function", _FILTER_HINT),
    ast.UnaryOp: ("arithmetic is not supported in a pipeline function", _FILTER_HINT),
    ast.BoolOp: ("boolean logic is not supported in a pipeline function", _CONDITION_HINT),
    ast.Compare: ("comparisons are not supported in a pipeline function", _CONDITION_HINT),
    ast.IfExp: ("conditional expressions (`a if c else b`) are not supported in a pipeline function", _CONDITION_HINT),
    ast.ListComp: ("comprehensions are not supported in a pipeline function", _LOOP_HINT),
    ast.SetComp: ("comprehensions are not supported in a pipeline function", _LOOP_HINT),
    ast.DictComp: ("comprehensions are not supported in a pipeline function", _LOOP_HINT),
    ast.GeneratorExp: ("generator expressions are not supported in a pipeline function", _LOOP_HINT),
    ast.Lambda: (
        "lambdas are not supported in a pipeline function",
        "define a named filter function (module level or enclosing function) and call it",
    ),
    ast.Subscript: (
        "indexing / slicing is not supported in a pipeline function",
        "make the filter return several outputs and unpack them (`a, b = split(img)`), or index inside a filter",
    ),
    ast.Attribute: (
        "attribute access is not supported in a pipeline function",
        f"read the attribute inside a filter; {_FILTER_HINT}",
    ),
    ast.Name: (
        "assigning a variable to another variable is not supported in a pipeline function",
        "use the original variable directly",
    ),
    ast.Constant: (
        "constants are not supported here in a pipeline function",
        "pass it as a literal keyword argument of a filter call (`amplify(img, gain=2.0)`), or as a control",
    ),
    ast.JoinedStr: ("f-strings are not supported in a pipeline function", _FILTER_HINT),
    ast.Dict: ("dict literals are not supported in a pipeline function", _FILTER_HINT),
    ast.Set: ("set literals are not supported in a pipeline function", _FILTER_HINT),
    ast.List: ("list literals are not supported here in a pipeline function", _FILTER_HINT),
    ast.Tuple: ("tuple literals are not supported here in a pipeline function", _FILTER_HINT),
    ast.NamedExpr: ("the walrus operator `:=` is not supported in a pipeline function", "use a plain assignment"),
    ast.Await: ("`await` is not supported in a pipeline function", "await inside a filter"),
    ast.Yield: ("`yield` is not supported in a pipeline function", "pipelines are not generators"),
    ast.YieldFrom: ("`yield from` is not supported in a pipeline function", "pipelines are not generators"),
    ast.Starred: ("star-unpacking is not supported in a pipeline function", "list every variable explicitly"),
}


def _parse_function_source(func: Callable) -> Tuple[ast.AST, int, List[str]]:
    """Parse the source of ``func`` (possibly defined in an indented scope).

    Returns (function AST node, line offset to add to node.lineno to get the
    absolute line number in the file, source lines).
    """
    name = getattr(func, "__name__", repr(func))
    try:
        source_lines, first_lineno = inspect.getsourcelines(func)
    except (OSError, TypeError) as exc:
        raise ValueError(
            f"cannot read the source code of pipeline '{name}' ({exc}): a pipeline function is analyzed "
            "statically, so it must be a regular `def` in a file or notebook cell "
            "(not built with exec/eval, not a builtin or a callable object)"
        ) from exc
    source = "".join(source_lines)
    line_offset = first_lineno - 1
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        # dedent fails when a multi-line string inside the body is less indented
        # than the def: nest the source in a dummy block instead.
        tree = ast.parse("if True:\n" + source)
        tree = ast.Module(body=tree.body[0].body, type_ignores=[])  # type: ignore[attr-defined]
        line_offset -= 1
    if not tree.body:  # type: ignore[attr-defined]
        raise ValueError("Function body is empty")
    main_function = tree.body[0]  # type: ignore[attr-defined]
    if not isinstance(main_function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError(
            f"pipeline '{name}' must be a regular `def` function (a lambda or an expression cannot be "
            "analyzed): write `def my_pipeline(img): out = my_filter(img); return out`"
        )
    return main_function, line_offset, source_lines


def _is_literal(node: ast.expr) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return True


def _is_native_callable(obj: Any) -> bool:
    """numpy ufuncs, C builtins and other callables without a usable Python signature."""
    if isinstance(obj, FilterCore) or inspect.isfunction(obj) or inspect.ismethod(obj):
        return False
    if inspect.isbuiltin(obj) or type(obj).__name__ == "ufunc":
        return True
    try:
        inspect.signature(obj)
    except (TypeError, ValueError):
        return True
    return False


def _positional_filter(obj: Callable, name: str) -> Callable:
    """Expose a native callable (``np.abs``) as a filter taking only its inputs.

    A filter receives every keyword argument of its signature explicitly, which
    native functions do not support (``np.abs(x, dtype=None, signature=None)``
    raises), so the wrapper forwards the positional inputs only.
    """

    def native_filter(*inputs):
        return obj(*inputs)

    native_filter.__name__ = name
    native_filter.__qualname__ = name
    native_filter.__doc__ = getattr(obj, "__doc__", None)
    return native_filter


class _PipelineParser:
    """Validate the top-level statements of a pipeline function and build its call graph."""

    def __init__(self, func: Callable, global_context: Optional[dict] = None):
        # a function already wrapped by @interactive_pipeline (functools.wraps):
        # analyze the user's function, in its own module and closure
        func = inspect.unwrap(func)
        self.func = func
        self.function_node, self.line_offset, self.source_lines = _parse_function_source(func)
        self.first_lineno = self.line_offset + 1
        self.pipeline_name = self.function_node.name  # type: ignore[attr-defined]
        try:
            self.filename = inspect.getsourcefile(func) or inspect.getfile(func)
        except TypeError:
            self.filename = None
        self.globals, self.nonlocals = self._scope(func, global_context)
        self.results: List[dict] = []
        self.hoisted_names: set = set()
        # variables a filter call may use as inputs: the pipeline arguments,
        # then the outputs of every filter call seen so far
        arguments = self.function_node.args  # type: ignore[attr-defined]
        self.defined_variables: set = {
            arg.arg for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
        }
        for extra in (arguments.vararg, arguments.kwarg):
            if extra is not None:
                self.defined_variables.add(extra.arg)

    @staticmethod
    def _scope(func: Callable, global_context: Optional[dict]) -> Tuple[dict, dict]:
        """Names visible from the pipeline body: closure variables first, then module globals."""
        nonlocals: dict = {}
        try:
            nonlocals = dict(inspect.getclosurevars(func).nonlocals)
        except TypeError:
            pass
        if global_context is None:
            global_context = getattr(func, "__globals__", None)
        if global_context is None:
            module = inspect.getmodule(func)
            global_context = module.__dict__ if module is not None else {}
        return global_context, nonlocals

    # ------------------------------------------------------------------ errors
    def error(self, node: ast.AST, message: str, hint: Optional[str] = None) -> PipelineSyntaxError:
        relative_line = getattr(node, "lineno", None)
        lineno = None
        source_line = None
        if relative_line is not None:
            lineno = relative_line + self.line_offset
            index = lineno - self.first_lineno
            if 0 <= index < len(self.source_lines):
                source_line = self.source_lines[index].rstrip("\n")
        return PipelineSyntaxError(
            message,
            pipeline_name=self.pipeline_name,
            filename=self.filename,
            lineno=lineno,
            source_line=source_line,
            hint=hint,
        )

    def expression_error(self, node: ast.AST, context: str = "") -> PipelineSyntaxError:
        description, hint = _EXPRESSION_ERRORS.get(
            type(node), (f"`{type(node).__name__}` expressions are not supported in a pipeline function", _FILTER_HINT)
        )
        if context:
            description = f"{description} ({context})"
        return self.error(node, description, hint)

    # ------------------------------------------------------- name resolution
    def _visible_names(self) -> List[str]:
        names = set(self.nonlocals) | {name for name in self.globals if not name.startswith("__")}
        return sorted(names)

    @staticmethod
    def _did_you_mean(name: str, candidates: Sequence[str]) -> str:
        matches = difflib.get_close_matches(name, list(candidates), n=3)
        if not matches:
            return ""
        return "did you mean " + " or ".join(f"'{match}'" for match in matches) + "?"

    def resolve_callable(self, call: ast.Call) -> Tuple[str, Any]:
        """Resolve the called object from the pipeline's real scope.

        ``flt(...)`` looks ``flt`` up in the closure then the module globals;
        ``lib.sub.flt(...)`` resolves ``lib`` the same way then follows the
        attribute chain. Returns (filter name, object); the filter name is the
        last name of the chain.
        """
        chain: List[str] = []
        node = call.func
        while isinstance(node, ast.Attribute):
            chain.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            raise self.error(
                call,
                "only named filters can be called in a pipeline function (`flt(img)` or `module.flt(img)`)",
                "assign the callable to a name outside the pipeline function and call it by that name",
            )
        root = node.id
        if chain and root in self.defined_variables:
            raise self.error(
                call,
                f"'{root}' is a variable of the pipeline: calling its method `{root}.{chain[0]}(...)` "
                "is not supported in a pipeline function",
                f"call `{chain[0]}` inside a filter function; {_FILTER_HINT}",
            )
        if root in self.nonlocals:
            obj = self.nonlocals[root]
        elif root in self.globals:
            obj = self.globals[root]
        else:
            if hasattr(builtins, root):
                raise self.error(
                    call,
                    f"'{root}' is a Python builtin, not a filter",
                    f"call `{root}` inside a filter function; {_FILTER_HINT}",
                )
            suggestion = self._did_you_mean(root, self._visible_names())
            raise self.error(
                call,
                f"name '{root}' is not defined in the scope of the pipeline function",
                suggestion or "define or import the filter before the pipeline function",
            )
        dotted = root
        for attr in reversed(chain):
            if not hasattr(obj, attr):
                candidates = [name for name in dir(obj) if not name.startswith("_")]
                suggestion = self._did_you_mean(attr, candidates)
                raise self.error(
                    call,
                    f"'{dotted}' has no attribute '{attr}'",
                    suggestion or f"check the spelling of '{dotted}.{attr}'",
                )
            obj = getattr(obj, attr)
            dotted += f".{attr}"
        function_name = chain[0] if chain else root
        if not isinstance(obj, FilterCore) and not callable(obj):
            raise self.error(
                call,
                f"'{dotted}' is not callable (it is a {type(obj).__name__})",
                "only filter functions or Filter instances can be called in a pipeline function",
            )
        return function_name, obj

    # ------------------------------------------------------------ statements
    def hoisted_name(self, call: ast.Call) -> str:
        """Name of the intermediate variable holding a nested call's result.

        The call's own source (``amplify(img)``) reads well as an output title
        and can never collide with a user variable, which must be an
        identifier. A repeated identical call gets a ``#2``, ``#3``... suffix.
        """
        base = ast.unparse(call)
        name = base
        count = 1
        while name in self.hoisted_names:
            count += 1
            name = f"{base} #{count}"
        self.hoisted_names.add(name)
        return name

    def hoist(self, call: ast.Call) -> str:
        """Turn a nested call into a node of its own and return its output name."""
        name = self.hoisted_name(call)
        self.call_entry(call, [name])
        return name

    @staticmethod
    def positional_parameter_hint(sig: Tuple[List[str], Dict[str, Any]], index: int, value: ast.expr) -> str:
        args, kwargs = sig
        keyword_names = list(kwargs)
        kw_index = index - len(args)
        literal = ast.unparse(value)
        if 0 <= kw_index < len(keyword_names):
            return f"pass it as a keyword argument: `{keyword_names[kw_index]}={literal}`"
        return "pass parameters as keyword arguments (`param=value`); positional arguments are filter inputs"

    def parse_args(self, call: ast.Call, sig: Tuple[List[str], Dict[str, Any]]) -> List[str]:
        input_names = []
        for index, arg in enumerate(call.args):
            if isinstance(arg, ast.Name):
                if arg.id not in self.defined_variables:
                    suggestion = self._did_you_mean(arg.id, sorted(self.defined_variables))
                    raise self.error(
                        arg,
                        f"'{arg.id}' is not a variable of the pipeline: filter inputs must be pipeline "
                        "arguments or outputs of an earlier filter call",
                        suggestion
                        or f"add `{arg.id}` to the arguments of the pipeline function, or produce it with a filter",
                    )
                input_names.append(arg.id)
            elif isinstance(arg, ast.Call):
                input_names.append(self.hoist(arg))
            elif isinstance(arg, ast.Starred):
                raise self.error(
                    arg, "star-unpacking of arguments (`f(*imgs)`) is not supported", "pass every input explicitly"
                )
            elif isinstance(arg, ast.Constant) or _is_literal(arg):
                raise self.error(
                    arg,
                    "positional literal arguments are not supported: positional arguments are filter inputs",
                    self.positional_parameter_hint(sig, index, arg),
                )
            else:
                raise self.expression_error(arg, "filter inputs must be variable names or filter calls")
        return input_names

    def parse_keywords(self, call: ast.Call, function_name: str, sig: Tuple[List[str], Dict[str, Any]]) -> dict:
        """Literal keyword arguments: ``amplify(img, gain=2.5)`` sets that instance's parameter."""
        args, kwargs = sig
        literal_kwargs = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                raise self.error(
                    keyword.value,
                    "`**kwargs` unpacking is not supported in a filter call",
                    "pass every keyword argument explicitly",
                )
            if keyword.arg not in kwargs:
                if keyword.arg in args:
                    raise self.error(
                        keyword.value,
                        f"'{keyword.arg}' is an input of filter '{function_name}', not a parameter",
                        "pass inputs positionally: `flt(img)`",
                    )
                suggestion = self._did_you_mean(keyword.arg, list(kwargs))
                available = ", ".join(kwargs) or "none"
                raise self.error(
                    keyword.value,
                    f"'{keyword.arg}' is not a parameter of filter '{function_name}' (parameters: {available})",
                    suggestion or "check the filter signature",
                )
            try:
                value = ast.literal_eval(keyword.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                raise self.error(
                    keyword.value,
                    f"the value of '{keyword.arg}' must be a literal (number, string, bool, None, tuple, list, dict)",
                    "the pipeline body is not executed, so variables cannot be passed: use a literal value, "
                    "or a control to make it tunable",
                ) from None
            literal_kwargs[keyword.arg] = value
        return literal_kwargs

    def check_input_count(self, call: ast.Call, function_name: str, function_object: Any, provided: int) -> None:
        """Raise when a filter call misses required inputs (it would only fail once the pipeline runs)."""
        if isinstance(function_object, FilterCore):
            function_object = function_object.apply
        try:
            parameters = inspect.signature(function_object).parameters.values()
        except (TypeError, ValueError):
            return  # no introspectable signature (native callable): checked at run time
        if any(param.kind is inspect.Parameter.VAR_POSITIONAL for param in parameters):
            return
        required = [
            param.name
            for param in parameters
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and param.default is inspect.Parameter.empty
        ]
        if provided < len(required):
            missing = ", ".join(required[provided:])
            raise self.error(
                call,
                f"filter '{function_name}' expects {len(required)} input{'s' if len(required) != 1 else ''} "
                f"({', '.join(required)}), got {provided}: missing {missing}",
                f"pass the missing input{'s' if len(required) - provided != 1 else ''} positionally, "
                f"e.g. `{function_name}({', '.join(required)})`",
            )

    def call_entry(self, call: ast.Call, output_names: Optional[List[str]]) -> dict:
        """Validate a filter call and append its node to the graph (after its hoisted inner calls)."""
        function_name, function_object = self.resolve_callable(call)
        if isinstance(function_object, FilterCore):
            function_object.check_apply_signature()
            sig = function_object.signature
        else:
            if _is_native_callable(function_object):
                function_object = _positional_filter(function_object, function_name)
            sig = analyze_apply_fn_signature(function_object)
        literal_kwargs = self.parse_keywords(call, function_name, sig)
        input_names = self.parse_args(call, sig)
        self.check_input_count(call, function_name, function_object, len(input_names))
        self.defined_variables.update(output_names or [])
        if isinstance(function_object, FilterCore):
            # Case of a filter instance
            # ---> forcing filter instance .name to be the name of the object used in the func
            function_object.name = function_name
            function_object.inputs = input_names  # type: ignore
            function_object.outputs = output_names if output_names is not None else []  # type: ignore
        entry = {
            "function_name": function_name,
            "function_object": function_object,
            "signature": {"args": sig[0], "kwargs": sig[1]},
            "args": input_names,
            "returns": output_names if output_names is not None else [],
            "kwargs": literal_kwargs,
            "location": self.location(call),
        }
        self.results.append(entry)
        return entry

    def location(self, node: ast.AST) -> dict:
        """Where a node is, to raise a PipelineSyntaxError from later build stages."""
        error = self.error(node, "")
        return {
            "pipeline_name": error.pipeline_name,
            "filename": error.filename,
            "lineno": error.lineno,
            "source_line": error.source_line,
        }

    def target_names(self, target: ast.expr) -> List[str]:
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            names = []
            for element in target.elts:
                if not isinstance(element, ast.Name):
                    raise self.error(
                        element,
                        "filter outputs must be unpacked into a flat list of variable names (`a, b = flt(img)`)",
                        "unpack into plain names, e.g. `a, b, c = flt(img)`",
                    )
                names.append(element.id)
            return names
        raise self.error(
            target,
            "filter outputs can only be assigned to variable names",
            "assign to plain names (`out = flt(img)`), not to attributes, items or starred targets",
        )

    def check_return_value(self, node: ast.expr) -> ast.expr:
        """Validate the returned structure; filter calls in it are hoisted and replaced by their output name."""
        if isinstance(node, ast.Name):
            if node.id not in self.defined_variables:
                suggestion = self._did_you_mean(node.id, sorted(self.defined_variables))
                raise self.error(
                    node,
                    f"'{node.id}' is returned but is not a variable of the pipeline",
                    suggestion or "return pipeline arguments or outputs of filter calls",
                )
            return node
        if isinstance(node, ast.Constant) and node.value is None:
            return node
        if isinstance(node, ast.Call):
            return ast.copy_location(ast.Name(id=self.hoist(node), ctx=ast.Load()), node)
        if isinstance(node, (ast.Tuple, ast.List)):
            elements = [self.check_return_value(element) for element in node.elts]
            return ast.copy_location(type(node)(elts=elements, ctx=ast.Load()), node)
        raise self.expression_error(
            node, "a pipeline returns variable names or filter calls, a tuple or (nested) list of them"
        )

    def parse(self) -> dict:
        body = self.function_node.body  # type: ignore[attr-defined]
        return_node: Optional[ast.Return] = None
        for index, statement in enumerate(body):
            if return_node is not None:
                raise self.error(
                    statement,
                    "statements after the `return` of a pipeline function are not supported",
                    "a pipeline returns once, as its last statement",
                )
            if isinstance(statement, ast.Pass):
                continue
            if isinstance(statement, ast.Expr):
                value = statement.value
                if isinstance(value, ast.Constant) and (isinstance(value.value, str) or value.value is Ellipsis):
                    continue  # docstring / string comment / `...`
                if isinstance(value, ast.Call):
                    entry = self.call_entry(value, None)
                    logging.debug(f"Function without assignment {entry['function_name']}")
                    continue
                raise self.expression_error(value, "a statement must be a filter call")
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                if isinstance(statement, ast.Assign):
                    targets = statement.targets
                    if len(targets) != 1:
                        raise self.error(
                            statement,
                            "chained assignment (`a = b = flt(img)`) is not supported in a pipeline function",
                            "assign the filter result to a single name (or unpack several outputs)",
                        )
                    target = targets[0]
                else:
                    target = statement.target
                value = statement.value
                if value is None:
                    raise self.error(
                        statement,
                        "bare annotations are not supported in a pipeline function",
                        "remove the annotation",
                    )
                output_names = self.target_names(target)
                if not isinstance(value, ast.Call):
                    raise self.expression_error(value, "the right-hand side must be a filter call")
                entry = self.call_entry(value, output_names)
                logging.debug(f"classic function with assignment {entry['function_name']}")
                continue
            if isinstance(statement, ast.Return):
                return_node = statement
                if statement.value is not None:
                    return_node = ast.Return(value=self.check_return_value(statement.value))
                continue
            description, hint = _STATEMENT_ERRORS.get(
                type(statement),
                (f"`{type(statement).__name__}` statements are not supported in a pipeline function", ACCEPTED_SYNTAX),
            )
            raise self.error(statement, description, hint)
        return {"call_graph": self.results, "returns": self.return_outputs(return_node)}

    @staticmethod
    def return_outputs(return_node: Optional[ast.Return]):
        if return_node is None or return_node.value is None:
            return None
        ret_node = return_node.value
        if isinstance(ret_node, (ast.List, ast.Tuple)):
            # Check if any element is itself a list/tuple (indicating 2D structure)
            has_nested_structure = any(isinstance(elt, (ast.List, ast.Tuple)) for elt in ret_node.elts)
            if has_nested_structure:
                # Preserve the nested structure for 2D output layouts
                return get_name(ret_node, preserve_structure=True)
            # Flatten for simple 1D lists/tuples (original behavior)
            return flatten_target_names([get_name(ret_node, preserve_structure=False)], mapping_function=None)
        # Single return value or name
        return flatten_target_names([get_name(ret_node, preserve_structure=False)], mapping_function=None)


def get_call_graph(func: Callable, global_context: Optional[dict] = None) -> dict:
    """Statically analyze a pipeline function into a call graph.

    Only the top-level statements of the function body are considered and
    each one is validated: see ``ACCEPTED_SYNTAX``. Called names are resolved
    in the function's real scope (closure variables, then module globals, or
    ``global_context`` when given), dotted calls by following the attribute
    chain.

    Raises:
        PipelineSyntaxError: for any statement that cannot be expressed in the
            graph, or a called name that cannot be resolved.
    """
    parser = _PipelineParser(func, global_context=global_context)
    parsed = parser.parse()
    inputs, kwargs = analyze_apply_fn_signature(parser.func)
    return {
        "function_name": parser.pipeline_name,
        "call_graph": parsed["call_graph"],
        "args": inputs,
        "kwargs": kwargs,
        "returns": parsed["returns"],
    }
