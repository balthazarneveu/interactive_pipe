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

### Pipeline functions cannot have `global_params` in their signature
These are automatically filled by the framework. Only filter functions (decorated with `@interactive()`) can have `global_params` in their signature, and it will be automatically injected.

```python
# ✅ CORRECT - filter function can have global_params
@interactive()
def my_filter(img, param=0.5, global_params={}):
    global_params["__output_styles"]["my_img"] = {"title": "My Image"}
    return img * param

# ✅ CORRECT - pipeline function does NOT have global_params
def my_pipeline(img_list):
    img = my_filter(img_list)
    return [img]

# ❌ WRONG - pipeline function should NOT have global_params
def my_pipeline(img_list, global_params={}):  # This won't work!
    img = my_filter(img_list)
    return [img]
```

To access `global_params` from helper functions called within the pipeline, access it via `global_params["__pipeline"].global_params` or pass it through filter functions.

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
