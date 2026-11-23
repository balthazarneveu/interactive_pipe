# Type checking

interactive_pipe ships type information (`py.typed`), so pipelines can be
checked by mypy and pyright, including their strict modes. Annotate your
filters like plain functions: the decorators keep their types.

```python
from typing import Annotated, List, Tuple

import numpy as np

from interactive_pipe import interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def amplify(img: np.ndarray, gain: float = 1.0) -> np.ndarray:
    return img * gain


@interactive
def split(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    return img[:, : img.shape[1] // 2], img[:, img.shape[1] // 2 :]


@interactive()
def blur(img: np.ndarray, radius: Annotated[int, (0, 10)] = 2) -> np.ndarray:
    return img


@interactive_pipeline(gui=None)
def process(img: np.ndarray) -> List[np.ndarray]:
    left, right = split(img)
    return [amplify(left, gain=2.0), blur(right)]


left, right = process(np.ones((8, 8, 3)), gain=1.5)
```

## What the decorators return

| Decorator | Static type | Notes |
| --- | --- | --- |
| `@interactive` / `@interactive(...)` | `InteractiveFilter[P, R]` | Calling it is checked against the filter's own parameters `P` and returns `R`. `.snapshot()`, `.sweep()`, `.describe()`, `.summary()` and `.interact()` are typed too. |
| `@interactive_pipeline(gui=None)` or `gui="headless"` | `HeadlessPipeline` | |
| `@interactive_pipeline(gui=...)` with any other value | `GuiPipelineApp` | Callable, with `.headless`, `.snapshot()`, `.sweep()`, `.describe()`, `.summary()`, `.graph_representation()` and `.pipeline` (the GUI object, e.g. `.pipeline.bind_key_to_context(...)`). |
| `@interact(...)` | the decorated function, unchanged | |

These types are exported from `interactive_pipe` for your own annotations
(`def run(app: PipelineApp) -> None`). `HeadlessPipeline` satisfies
`PipelineApp`.

On Python 3.9, write `InteractiveFilter[..., T]` as a string annotation
(`-> "InteractiveFilter[..., np.ndarray]"`): before 3.10 a generic class cannot
take `...` at runtime.

The pipeline function's own annotations are only documentation: its body is
parsed, not executed (see [Decorators](decorators.md)). Calling a pipeline
accepts parameter overrides as keywords (`process(img, gain=1.5)`), so it is
typed as `(*args, **kwargs) -> Any`.

## Running the checkers

<!-- code: skip shell commands -->
```python
# pip install "interactive_pipe[dev]"   (ruff, pyright, mypy)
# mypy --strict my_pipeline.py
# pyright my_pipeline.py
```

When PyQt6 is installed, mypy stops on its stub files (a syntax its parser
rejects). This is not specific to interactive_pipe: Pillow's `PIL.ImageQt`
imports PyQt6, so a file containing only `import PIL.Image` fails the same way.
Skip the PyQt stubs:

```ini
# mypy.ini
[mypy-PyQt6.*,PyQt5.*]
follow_imports = skip
follow_imports_for_stubs = True
```

## Tips

- Paths accept `str` or `pathlib.Path` (`Image.load_image("photo.png")`).
- `Curve`, `Table` and control ranges accept any sequence (lists, tuples,
  numpy columns), so a `List[SingleCurve]` variable or `ylim=[0, 1]`
  type-checks.
- `context["key"]` and `Control.value` are `Any`: annotate the variable you
  read them into (`gain: float = context["gain"]`).
- The `demo/` scripts are fully annotated (pyright clean, `mypy --strict`
  clean apart from numpy functions returning `Any`): they are examples of
  typed pipelines.
