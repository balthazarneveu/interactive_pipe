<div align="center">

![Interactive pipe](https://raw.githubusercontent.com/balthazarneveu/interactive_pipe/master/static/interact-pipe-logo-horizontal-rgb.svg)

[![PyPI](https://img.shields.io/pypi/v/interactive-pipe)](https://pypi.org/project/interactive-pipe/)
[![Python versions](https://img.shields.io/pypi/pyversions/interactive-pipe)](https://pypi.org/project/interactive-pipe/)
[![License](https://img.shields.io/github/license/balthazarneveu/interactive_pipe)](https://github.com/balthazarneveu/interactive_pipe/blob/master/LICENSE)
[![Docs](https://img.shields.io/badge/docs-mkdocs%20material-blue)](https://balthazarneveu.github.io/interactive_pipe/)
[![Interactive pipe python package](https://github.com/balthazarneveu/interactive_pipe/actions/workflows/pytest.yaml/badge.svg)](https://github.com/balthazarneveu/interactive_pipe/actions/workflows/pytest.yaml)

**📖 [Documentation](https://balthazarneveu.github.io/interactive_pipe/)**

</div>

# interactive_pipe

**Turn plain python processing functions into an interactive GUI app — without writing a single line of GUI code.**

```bash
pip install interactive-pipe
```

- Develop an algorithm while debugging visually with plots, checking robustness and continuity to parameter changes.
- Magically create a graphical interface to demonstrate a concept or tune your algorithm.
- Keep your algorithm library untouched: interactivity is added by decoration, not by rewriting.
- The same pipeline runs headless for batch processing and tests.

![Interactive pipe demo](https://raw.githubusercontent.com/balthazarneveu/interactive_pipe/master/docs/images/demo_multi_image.gif)

## Quick taste

```python
from interactive_pipe import interactive, interactive_pipeline
import numpy as np

@interactive(coeff=(1.0, [0.5, 2.0], "exposure"), bias=(0.0, [-0.2, 0.2]))
def exposure(img, coeff=1.0, bias=0.0):
    return img * coeff + bias

@interactive(blend_coeff=(0.5, [0.0, 1.0]))
def blend(img0, img1, blend_coeff=0.5):
    return (1 - blend_coeff) * img0 + blend_coeff * img1

@interactive_pipeline(gui="qt")  # or "mpl", "nb" (Jupyter/Colab), "gradio"
def pipe(img):
    exposed = exposure(img)
    blended = blend(img, exposed)
    return exposed, blended

pipe(np.array([0.0, 0.5, 0.8]) * np.ones((256, 512, 3)))
```

Calling `pipe(...)` opens a window with sliders for every declared parameter. 🎉

## Backends

| *PyQt / PySide* | *Matplotlib* | *Jupyter / Colab* | *Gradio* |
|:-----:|:------:|:----:|:----:|
| `gui="qt"` | `gui="mpl"` | `gui="nb"` | `gui="gradio"` |
| ![qt](https://raw.githubusercontent.com/balthazarneveu/interactive_pipe/master/docs/images/qt_backend.jpg) | ![mpl](https://raw.githubusercontent.com/balthazarneveu/interactive_pipe/master/docs/images/mpl_backend.jpg) | ![nb](https://raw.githubusercontent.com/balthazarneveu/interactive_pipe/master/docs/images/notebook_backend.jpg) | ![gradio](https://raw.githubusercontent.com/balthazarneveu/interactive_pipe/master/docs/images/gradio_backend.jpg) |

Plus headless mode (`gui=None`) for batch processing. Full feature matrix in the [backends docs](https://balthazarneveu.github.io/interactive_pipe/getting-started/backends/).

## Learn more

- 📖 [Documentation](https://balthazarneveu.github.io/interactive_pipe/) — quickstart, guides, API reference
- 🤖 Agent-friendly docs: [llms.txt](https://balthazarneveu.github.io/interactive_pipe/llms.txt) / [llms-full.txt](https://balthazarneveu.github.io/interactive_pipe/llms-full.txt)
- 🎓 [Interactive tutorial on Hugging Face](https://huggingface.co/spaces/balthou/interactive-pipe-tutorial)
- 🗒️ [Examples gallery](https://balthazarneveu.github.io/interactive_pipe/guide/examples/) — 17 demo scripts, Colab notebooks, a Raspberry Pi jukebox
- 📋 [Changelog](https://github.com/balthazarneveu/interactive_pipe/blob/master/CHANGELOG.md)
- 🤝 [Contributing](https://github.com/balthazarneveu/interactive_pipe/blob/master/CONTRIBUTING.md)
