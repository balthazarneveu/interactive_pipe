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
  ./venv/bin/python -m black .
  ./venv/bin/python -m flake8
  ```
- Fix any linting errors before committing
- Black will auto-format; commit those changes with your code

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

### Pipeline functions must contain ONLY function calls
No control flow statements (if/else/for/while). The AST parser analyzes the pipeline function to build the execution graph, and it only understands function calls. If you need conditional logic, handle it inside individual filter functions instead.

```python
# ✅ CORRECT - only function calls
def my_pipeline(img_list):
    img = select_image(img_list)
    processed = process_image(img)
    return [img, processed]

# ❌ WRONG - contains if statement
def my_pipeline(img_list):
    img = select_image(img_list)
    if some_condition:  # This will break the AST parser!
        return [img]
    else:
        return [img, processed]
```

### Use the new context API instead of `global_params={}` or `context={}`

The old `global_params={}` or `context={}` keyword argument pattern is deprecated. Use the new clean API with `context` and `layout` proxies instead.

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

# ❌ WRONG - using deprecated global_params={}
@interactive()
def my_filter(img, param=0.5, global_params={}):  # Deprecated!
    global_params["__output_styles"]["my_img"] = {"title": "My Image"}
    return img * param
```

**Key points:**
- Import `context` and `layout` from `interactive_pipe`
- Use `layout.style("output_name", title=...)` instead of `global_params["__output_styles"]`
- Use `context["key"]` or `context.key` for sharing data between filters
- No need for `global_params={}` in function signatures anymore

## Project Structure

- Source code: `src/interactive_pipe/`
- Tests: `test/`
- Virtual environment: `venv/`

## Common Commands

```bash
# Format code
./venv/bin/python -m black .

# Lint code
./venv/bin/python -m flake8

# Run all tests
./venv/bin/python -m pytest test/ -v --tb=short

# Run specific test file
./venv/bin/python -m pytest test/test_core.py -v

# Pre-commit checklist (run all before committing)
./venv/bin/python -m black .
./venv/bin/python -m flake8
./venv/bin/python -m pytest test/ -v --tb=short
git add <files>
git commit -m "message"
```
