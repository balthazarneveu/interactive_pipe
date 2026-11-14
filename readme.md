<div align="center">

![Interactive pipe](static/interact-pipe-logo-horizontal-rgb.svg)

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

![Interactive pipe demo](docs/images/demo_multi_image.gif)

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


@interactive_pipeline(gui="qt")  # or "dpg" (Dear PyGui), "mpl", "nb" (Jupyter/Colab), "gradio"
def pipe(img):
    exposed = exposure(img)
    blended = blend(img, exposed)
    return exposed, blended


pipe(np.array([0.0, 0.5, 0.8]) * np.ones((256, 512, 3)))
```

Calling `pipe(...)` opens a window with sliders for every declared parameter. 🎉

## Works without a display

- `pipe.snapshot("out.png", img, coeff=1.5)` renders what the window shows to a PNG (any `gui=`, no window).
- `pipe.sweep("sweep.png", img, coeff=[0.5, 1.0, 2.0])` compares parameter values side by side.
- `interactive-pipe snapshot my_script.py` runs an unmodified GUI script and writes one PNG per pipeline call.

## Using it with a coding agent

```bash
interactive-pipe skill --install            # Claude Code skill in ~/.claude/skills/ (or --project DIR)
interactive-pipe skill --agents-md          # a short block for your AGENTS.md / CLAUDE.md
interactive-pipe describe my_script.py      # controls and outputs, as text or --json
interactive-pipe doctor                     # installed backends, display, what gui="auto" picks
```

The skill teaches the agent the decorators, what a pipeline body may contain, and to check its visual work by reading snapshots. `python -m interactive_pipe ...` works too; see [Command line & coding agents](https://balthazarneveu.github.io/interactive_pipe/guide/command-line/).

## Backends

| *PyQt / PySide* | *Matplotlib* | *Jupyter / Colab* | *Gradio* |
|:-----:|:------:|:----:|:----:|
| `gui="qt"` | `gui="mpl"` | `gui="nb"` | `gui="gradio"` |
| ![qt](docs/images/qt_backend.jpg) | ![mpl](docs/images/mpl_backend.jpg) | ![nb](docs/images/notebook_backend.jpg) | ![gradio](docs/images/gradio_backend.jpg) |

Plus a GPU-rendered [Dear PyGui](https://github.com/hoffstadt/DearPyGui) window (`gui="dpg"`, `pip install "interactive-pipe[dpg]"`) and headless mode (`gui=None`) for batch processing. Full feature matrix in the [backends docs](https://balthazarneveu.github.io/interactive_pipe/getting-started/backends/).

## Learn more

- 📖 [Documentation](https://balthazarneveu.github.io/interactive_pipe/) — quickstart, guides, API reference
- 🤖 Agent-friendly docs: [llms.txt](https://balthazarneveu.github.io/interactive_pipe/llms.txt) / [llms-full.txt](https://balthazarneveu.github.io/interactive_pipe/llms-full.txt)
- 🎓 [Interactive tutorial on Hugging Face](https://huggingface.co/spaces/balthou/interactive-pipe-tutorial)
- 📸 [Snapshots & sweeps](https://balthazarneveu.github.io/interactive_pipe/guide/snapshots/) — render what the GUI shows to a PNG, headless (CI, SSH, coding agents)
- 💻 [Command line & coding agents](https://balthazarneveu.github.io/interactive_pipe/guide/command-line/) — `interactive-pipe skill / doctor / snapshot / describe`
- 🗒️ [Examples gallery](https://balthazarneveu.github.io/interactive_pipe/guide/examples/) — 17 demo scripts, Colab notebooks, a Raspberry Pi jukebox
- 📋 [Changelog](https://github.com/balthazarneveu/interactive_pipe/blob/master/CHANGELOG.md)
- 🤝 [Contributing](https://github.com/balthazarneveu/interactive_pipe/blob/master/CONTRIBUTING.md)
