# Interactive Pipe - AI Assistant Guide

## Project Overview

A Python library for creating interactive image/signal processing pipelines with automatic GUI generation. Supports multiple backends: PyQt (qt), Matplotlib (mpl), Jupyter notebooks (nb), and Gradio.

**Key concept**: Decorate functions with `@interactive()` to turn keyword arguments into sliders/widgets, then compose them with `@interactive_pipeline()` to create a full GUI application.

## Setup

```bash
source venv/bin/activate
pip install -e ".[full]"  # Install with all optional dependencies
```

### Optional dependency groups
- `qt6` / `qt5` - PyQt GUI backend
- `notebook` - Jupyter ipywidgets support
- `pytest` - Testing dependencies
- `full` - Everything including Gradio

## Development Commands

**Format (Black):**
```bash
black .
```

**Lint (flake8):**
```bash
flake8 .
```

**Test:**
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
**Check formatting without modifying (CI-style):**
```bash
black --check .
```

## Project Structure

```
src/interactive_pipe/
├── core/           # Pipeline engine, filters, caching, DAG graph
├── data_objects/   # Image, Curve, Audio data types
├── graphical/      # GUI backends (qt, mpl, nb, gradio)
├── headless/       # Non-GUI control mechanisms
└── helper/         # Decorators (@interactive, @interactive_pipeline)

test/               # pytest tests
demo/               # Example applications
samples/            # Code samples and tutorials
```

## Key APIs

Main imports from `interactive_pipe`:
- `@interactive()` - Decorator to make filter functions interactive
- `@interactive_pipeline()` - Decorator to create GUI pipelines
- `Control`, `KeyboardControl`, `CircularControl` - Manual control definitions
- `Image`, `Curve` - Data wrapper classes

### Basic usage pattern:
```python
from interactive_pipe import interactive, interactive_pipeline

@interactive()
def my_filter(img, param=(0.5, [0., 1.], "label")):
    return img * param

@interactive_pipeline(gui="qt")  # or "mpl", "nb", "gradio"
def my_pipeline(input_image):
    return my_filter(input_image)
```

### Important Constraints

**Pipeline functions must contain ONLY function calls** - no control flow statements (if/else/for/while).
The AST parser analyzes the pipeline function to build the execution graph, and it only understands function calls.
If you need conditional logic, handle it inside individual filter functions instead.

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

**Pipeline functions cannot have `global_params` or other dedicated keywords in their signature** - these are automatically filled by the framework. Only filter functions (decorated with `@interactive()`) can have `global_params` in their signature, and it will be automatically injected.

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

## Testing

Tests are in `test/` directory. CI runs pytest on Python 3.9, 3.10, 3.11.

```bash
pytest                    # Run all tests
pytest test/test_core.py  # Run specific test file
pytest -v                 # Verbose output
```

## Code Style

- **Line length**: 120 characters (flake8), 119 (isort)
- **Formatter**: Black
- **Linter**: flake8 (excludes `__init__.py` and venv)

## CI Workflows

- `formatting.yaml` - Black formatting check
- `flake8.yaml` - Linting check  
- `pytest.yaml` - Tests on Python 3.9/3.10/3.11
