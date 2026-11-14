"""Grade a show-reel demo script without opening a window.

    python showreel/tools/grade.py path/to/demo.py --out /some/dir --max-lines 80

The demo is run as a script with every backend forced to headless, the
pipeline it launches is captured, and each control is swept over its range.

Checks
- static: the pipeline body holds only filter calls, no removed context kwarg,
  line budget (blank lines, comments and docstrings are not counted)
- runs with the default parameters, outputs are finite
- every control changes at least one output and never raises
- run time at default (a slider must stay usable)

Default outputs are written to --out as PNG / txt for a visual review.
Exit code 0 when no check failed.
"""

import argparse
import ast
import hashlib
import json
import os
import runpy
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

REMOVED_KWARGS = {"global_params", "global_parameters", "global_state", "global_context", "context", "state"}
PIPELINE_DECORATORS = {"interactive_pipeline", "pipeline"}
SLOW_RUN_SECONDS = 1.0


def decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    return target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")


def is_plain_call_arg(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(is_plain_call_arg(elt) for elt in node.elts)
    return False


def is_filter_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and all(is_plain_call_arg(arg) for arg in node.args)
        and not node.keywords
    )


def static_checks(source: str, max_lines: int) -> dict:
    tree = ast.parse(source)
    problems, pipelines = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        all_args = node.args.args + node.args.kwonlyargs
        removed = sorted(arg.arg for arg in all_args if arg.arg in REMOVED_KWARGS)
        if removed:
            problems.append(f"{node.name}: removed context kwarg in signature: {removed}")
        if not any(decorator_name(deco) in PIPELINE_DECORATORS for deco in node.decorator_list):
            continue
        pipelines.append(node.name)
        for stmt in node.body:
            is_docstring = isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            is_call = isinstance(stmt, (ast.Assign, ast.Expr)) and is_filter_call(stmt.value)
            is_return = isinstance(stmt, ast.Return) and (stmt.value is None or is_plain_call_arg(stmt.value))
            if not (is_docstring or is_call or is_return):
                problems.append(f"{node.name}: line {stmt.lineno} is not a plain filter call: {ast.unparse(stmt)[:80]}")
    docstring_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(node) is not None:
            docstring_lines.update(range(node.body[0].lineno, node.body[0].end_lineno + 1))
    code_lines = [
        line
        for number, line in enumerate(source.splitlines(), start=1)
        if line.strip() and not line.strip().startswith("#") and number not in docstring_lines
    ]
    if not pipelines:
        problems.append("no function decorated with @interactive_pipeline at module level")
    if len(code_lines) > max_lines:
        problems.append(f"{len(code_lines)} code lines, budget is {max_lines}")
    return {"pipelines": pipelines, "code_lines": len(code_lines), "problems": problems}


def capture_pipeline(script: Path):
    """Run the script headless and return [(pipeline, positional inputs, keyword arguments)]."""
    import interactive_pipe.helper.pipeline_decorator as pipeline_decorator
    from interactive_pipe.headless.pipeline import HeadlessPipeline

    calls = []
    original_call = HeadlessPipeline.__call__

    def recording_call(self, *args, **kwargs):
        calls.append((self, args, kwargs))
        return original_call(self, *args, **kwargs)

    pipeline_decorator.resolve_gui = lambda gui: None  # every backend becomes headless
    HeadlessPipeline.__call__ = recording_call
    old_argv, old_path = sys.argv, list(sys.path)
    sys.argv = [str(script)]
    sys.path.insert(0, str(script.parent))
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        HeadlessPipeline.__call__ = original_call
        sys.argv, sys.path[:] = old_argv, old_path
    return calls


def flatten(outputs) -> list:
    if outputs is None:
        return []
    if isinstance(outputs, (list, tuple)):
        return [leaf for item in outputs for leaf in flatten(item)]
    return [outputs]


def fingerprint(obj) -> str:
    from interactive_pipe import Curve, Table

    if isinstance(obj, np.ndarray):
        payload = obj.tobytes()
    elif isinstance(obj, Curve):
        payload = b"".join(np.asarray(part).tobytes() for curve in obj.curves for part in (curve.x, curve.y))
        payload += repr((obj.title, obj.xlim, obj.ylim, [curve.label for curve in obj.curves])).encode()
    elif isinstance(obj, Table):
        payload = repr((obj.columns, obj.values, obj.title)).encode()
    elif hasattr(obj, "detach"):  # torch tensor
        payload = obj.detach().cpu().numpy().tobytes()
    else:
        payload = repr(obj).encode()
    return hashlib.md5(payload).hexdigest()


def describe(obj) -> str:
    from interactive_pipe import Curve, Table

    if isinstance(obj, np.ndarray):
        finite = bool(np.isfinite(obj).all()) if obj.dtype.kind == "f" else True
        return (
            f"array {obj.shape} {obj.dtype} range [{obj.min():.3g}, {obj.max():.3g}]{'' if finite else ' NOT FINITE'}"
        )
    if isinstance(obj, Curve):
        return f"Curve '{obj.title}' with {len(obj.curves)} curve(s)"
    if isinstance(obj, Table):
        return f"Table '{obj.title}' {len(obj.values)} row(s) x {len(obj.columns)} column(s)"
    return f"{type(obj).__name__}: {str(obj)[:60]}"


def dump(obj, path: Path) -> None:
    from PIL import Image

    from interactive_pipe import Curve, Table

    if isinstance(obj, np.ndarray) and obj.ndim in (2, 3):
        img = np.clip(np.nan_to_num(obj.astype(np.float64)), 0.0, 1.0)
        Image.fromarray((img * 255 + 0.5).astype(np.uint8).squeeze()).save(path.with_suffix(".png"))
    elif isinstance(obj, Curve):
        obj.save(path.with_suffix(".png"))
    elif isinstance(obj, Table):
        rows = [obj.columns] + [[str(value) for value in row] for row in obj.values]
        path.with_suffix(".txt").write_text(f"{obj.title}\n" + "\n".join(" | ".join(map(str, row)) for row in rows))
    else:
        path.with_suffix(".txt").write_text(str(obj))


def sweep_values(ctrl) -> list:
    from interactive_pipe import RangeControl, TimeControl

    default, value_range = ctrl.value_default, ctrl.value_range
    if isinstance(ctrl, TimeControl):
        return [0.37, 1.3, 2.9]
    if isinstance(ctrl, RangeControl):
        lo, hi = value_range
        mid = type(lo)((lo + hi) / 2)
        return [(lo, mid), (mid, hi), (lo, hi)]
    if isinstance(default, bool):
        return [not default]
    if isinstance(default, str):
        return [choice for choice in (value_range or []) if choice != default]
    if value_range is not None:
        return [value for value in value_range if value != default]
    return []  # free numeric / text parameter: nothing sensible to sweep


def run_with(pipe, filter_name=None, param=None, value=None):
    """Run the pipeline (optionally with one parameter changed) and return (outputs, seconds)."""
    if filter_name is not None:
        pipe.parameters = {filter_name: {param: value}}
    start = time.perf_counter()
    outputs = flatten(pipe.run())
    return outputs, time.perf_counter() - start


def dynamic_checks(script: Path, out_dir: Path) -> dict:
    report = {"problems": [], "warnings": [], "controls": [], "outputs": []}
    calls = capture_pipeline(script)
    if not calls:
        report["problems"].append("the script never called a pipeline (nothing launched under __main__?)")
        return report
    pipe = calls[-1][0]
    report["filters"] = [filt.name for filt in pipe.filters]
    report["cache"] = repr(getattr(pipe, "cache", None))
    controls = [
        (ctrl.filter_to_connect.name, ctrl.parameter_name_to_connect, ctrl)
        for ctrl in getattr(pipe, "controls", [])
        if ctrl.filter_to_connect is not None
    ]
    defaults = {(filter_name, param): ctrl.value_default for filter_name, param, ctrl in controls}

    def reset():
        for (filter_name, param), default in defaults.items():
            pipe.parameters = {filter_name: {param: default}}

    reset()
    reference, seconds = run_with(pipe)
    _, seconds_warm = run_with(pipe)
    report["seconds_first_run"], report["seconds_default"] = round(seconds, 3), round(seconds_warm, 3)
    if seconds_warm > SLOW_RUN_SECONDS:
        report["warnings"].append(f"default run takes {seconds_warm:.2f} s: sliders will lag")
    reference_prints = [fingerprint(out) for out in reference]
    for index, out in enumerate(reference):
        report["outputs"].append(describe(out))
        if "NOT FINITE" in report["outputs"][-1]:
            report["problems"].append(f"output {index} holds NaN or inf at default parameters")
        dump(out, out_dir / f"default_{index}")
    if not reference:
        report["problems"].append("the pipeline returns nothing")

    for filter_name, param, ctrl in controls:
        entry = {
            "control": f"{filter_name}.{param}",
            "type": type(ctrl).__name__,
            "default": repr(ctrl.value_default),
            "range": repr(ctrl.value_range),
            "group": getattr(getattr(ctrl, "panel", None), "name", None),
        }
        changed, slowest = False, 0.0
        for value in sweep_values(ctrl):
            reset()
            try:
                outputs, seconds = run_with(pipe, filter_name, param, value)
            except Exception as exc:  # report every failing value, keep sweeping
                report["problems"].append(f"{entry['control']}={value!r} raised {type(exc).__name__}: {exc}")
                pipe.reset_cache()
                continue
            slowest = max(slowest, seconds)
            changed = changed or [fingerprint(out) for out in outputs] != reference_prints
            for index, out in enumerate(outputs):
                if isinstance(out, np.ndarray) and out.dtype.kind == "f" and not np.isfinite(out).all():
                    report["problems"].append(f"{entry['control']}={value!r}: output {index} holds NaN or inf")
        entry["changes_output"], entry["slowest_seconds"] = changed, round(slowest, 3)
        if sweep_values(ctrl) and not changed:
            report["problems"].append(f"{entry['control']} has no effect on any output")
        if slowest > SLOW_RUN_SECONDS:
            report["warnings"].append(f"{entry['control']}: a run takes {slowest:.2f} s")
        report["controls"].append(entry)
    if not controls:
        report["problems"].append("no control declared: nothing is interactive")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="folder for the report and the default outputs")
    parser.add_argument("--max-lines", type=int, default=80, help="budget of non-blank, non-comment lines")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report = {"script": str(args.script), "static": static_checks(args.script.read_text(), args.max_lines)}
    try:
        report["dynamic"] = dynamic_checks(args.script.resolve(), args.out)
    except BaseException as exc:  # SystemExit from the script included: a crash is a finding, not a grader failure
        report["dynamic"] = {"problems": [f"crashed: {type(exc).__name__}: {exc}"], "traceback": traceback.format_exc()}
    problems = report["static"]["problems"] + report["dynamic"]["problems"]
    report["passed"] = not problems
    (args.out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("\nPASSED" if report["passed"] else f"\nFAILED ({len(problems)} problem(s))")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
