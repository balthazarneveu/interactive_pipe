# Claude AI Instructions for interactive_pipe

## Environment Setup

- **Always use the virtual environment** for running Python commands:
  ```bash
  ./venv/bin/python -m pytest test/ -v
  ```
- Do not use system Python (`python3`) directly as it may lack dependencies

## Development Workflow

### 1. Run Tests Frequently
- Run pytest after making changes to verify nothing is broken
- Use `--tb=short` for concise error output:
  ```bash
  ./venv/bin/python -m pytest test/ -v --tb=short
  ```
- Fix any broken tests before committing

### 2. Format and Lint Before Committing
- **Always run before each commit:**
  ```bash
  ./venv/bin/python -m ruff format .
  ./venv/bin/python -m ruff check --fix .
  ```
- Fix any linting errors before committing
- Ruff will auto-format and auto-fix many issues; commit those changes with your code
- Optional: Run `./venv/bin/python -m pyright` for type checking (informational only)

### 3. Make Small, Focused Commits
- Each commit should address **one logical change**
- Bundle related test changes with their corresponding source changes
- Don't create a separate "fix tests" commit at the end

### 4. Commit Message Format
- Use clear, descriptive commit messages
- Include context about what was changed and why
- Example:
  ```
  Replace assertions with proper exceptions in Control class
  
  - ValueError for invalid parameter values and ranges
  - TypeError for wrong types
  - Updated tests to expect new exception types
  ```

### 5. Code Quality Standards
- Replace `assert` statements with proper exceptions (`ValueError`, `TypeError`, `RuntimeError`)
- Fix mutable default arguments (`def func(param=[])` → `def func(param=None)`)
- Use proper type hints with `Optional` for nullable parameters
- Fix typos when encountered

## Important Constraints

### Pipeline function bodies are parsed, not executed — only filter calls are allowed
The pipeline function is analyzed statically (`core/graph.py`) to build the execution graph. Every top-level statement is validated; anything unsupported raises `PipelineSyntaxError` (a `ValueError`, exported from `interactive_pipe`) at build time, with the file, line, offending source line and a hint. Accepted:
- docstring, `pass`, `...`
- filter calls, assigned or not: `out = f(img)`, `a, b = f(img)`, `f(img)`, `gen()`
- nested calls `blur(amplify(img))` and `return amplify(img)` (the inner result is auto-named after its source, e.g. `amplify(img)`)
- literal keyword arguments `amplify(img, gain=2.5)` (sets that instance's value / control default; validated)
- dotted calls `np.abs(img)`, `lib.blur(img)`; names are resolved in the function's real scope (closure, then module globals), so pipelines may be defined inside `main()` or a test function
- one final `return` of names / tuples / (nested) lists / `None` / calls

Rejected with a hint: `if`/`for`/`while`/`with`/`try`, arithmetic and any non-call expression, `+=`, comprehensions, lambdas, statements after `return`, `*args`/`**kwargs`, positional literals (`blur(img, 3)`), non-literal keyword values, builtins, unknown names. If you need conditional logic, handle it inside individual filter functions instead.

```python
# ✅ CORRECT - only filter calls
def my_pipeline(img_list):
    img = select_image(img_list)
    processed = process_image(img, strength=0.5)
    return [img, processed]


# ❌ WRONG - raises PipelineSyntaxError ("`if` statements are not supported ...
#    Hint: move the condition inside a filter")
def my_pipeline(img_list):
    img = select_image(img_list)
    if some_condition:
        return [img]
    else:
        return [img, processed]
```

### Use the context API — `global_params={}` / `context={}` kwargs were REMOVED in 0.9.0

The old `global_params={}` or `context={}` keyword argument pattern was removed in 0.9.0: declaring one of these magic names (`global_params`, `global_parameters`, `global_state`, `global_context`, `context`, `state`) in a filter signature now raises `TypeError` at filter construction. Use the clean API with `context` and `layout` proxies instead.

```python
# ✅ CORRECT - using new context and layout API
from interactive_pipe import interactive, context, layout


@interactive()
def my_filter(img, param=0.5):
    layout.style("my_img", title="My Image")
    context["shared_data"] = "value"  # Share data between filters
    return img * param


# ✅ CORRECT - pipeline function (no context parameter needed)
def my_pipeline(img_list):
    img = my_filter(img_list)
    return [img]


# ❌ WRONG - removed global_params={} pattern (raises TypeError since 0.9.0)
@interactive()
def my_filter(img, param=0.5, global_params={}):  # TypeError at construction!
    global_params["__output_styles"]["my_img"] = {"title": "My Image"}
    return img * param
```

**Key points:**
- Import `context` and `layout` from `interactive_pipe`
- Use `layout.style("output_name", title=...)` instead of `global_params["__output_styles"]`
- Use `context["key"]` or `context.key` for sharing data between filters
- No need for `global_params={}` in function signatures anymore

## Checking visual output without a display

A GUI window cannot be looked at from here: render it to a PNG and read the file.

```python
print(pipe.summary())  # controls, ranges, outputs
pipe.snapshot("/tmp/out.png", img, gain=2.0)  # what the window would show
pipe.sweep("/tmp/sweep.png", img, gain=[0.5, 1, 2])  # compare values side by side
my_filter.snapshot("/tmp/f.png", img)  # a single @interactive filter
```

Works with any `gui=` value; overrides apply to the call only. For an unmodified
GUI script: `INTERACTIVE_PIPE_SNAPSHOT=/tmp/shots/ python demo/some_demo.py`.
See `docs/guide/snapshots.md`.

## Scientific outputs

Filters may also return a matplotlib `Figure`/`Axes` (rasterised once in
`graphical/display.py::prepare_display`, the single conversion point shared by
all backends, snapshot, Gradio refresh and `export_animation` — add new output
handling there, not per backend) and `interactive_pipe.Image`. Heatmap
options (`colormap`, `vmin`, `vmax`, `center`, `colorbar`, `unit`, `dpi`) go
through `layout.style`. `interactive_pipe.draw` draws marks on images. See
`docs/guide/figures-and-overlays.md`.

## Project Structure

- Source code: `src/interactive_pipe/`
- Tests: `test/`
- Virtual environment: `venv/`

## Common Commands

```bash
# Format code
./venv/bin/python -m ruff format .

# Lint code (with auto-fix)
./venv/bin/python -m ruff check --fix .

# Type check (optional, informational)
./venv/bin/python -m pyright

# Run all tests
./venv/bin/python -m pytest test/ -v --tb=short

# Run specific test file
./venv/bin/python -m pytest test/test_core.py -v

# Pre-commit checklist (run all before committing)
./venv/bin/python -m ruff format .
./venv/bin/python -m ruff check --fix .
./venv/bin/python -m pyright  # Optional, won't block commit
./venv/bin/python -m pytest test/ -v --tb=short
git add <files>
git commit -m "message"
```
