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
