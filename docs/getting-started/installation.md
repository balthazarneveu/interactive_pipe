# Installation

```bash
pip install interactive-pipe
```

The core package depends only on numpy, matplotlib, Pillow and PyYAML — the matplotlib backend works out of the box.

## Optional extras

| Extra | Installs | When you need it |
|---|---|---|
| `qt6` | PyQt6 | The Qt backend (`gui="qt"`), richest feature set |
| `qt5` | PyQt5 | Qt backend on systems without Qt6 support |
| `notebook` | ipywidgets | The Jupyter backend (`gui="nb"`), incl. Google Colab |
| `full` | Qt6 + OpenCV + ipywidgets + pandas + gradio + pytest | Everything |

```bash
pip install "interactive-pipe[qt6]"       # Qt backend
pip install "interactive-pipe[notebook]"  # Jupyter / Colab
pip install "interactive-pipe[full]"      # everything
```

Gradio (`gui="gradio"`) needs `pip install gradio` (included in `full`).

## From source

```bash
git clone git@github.com:balthazarneveu/interactive_pipe.git
cd interactive_pipe
pip install -e ".[full]"
```

## Tested platforms

- ✅ Linux (Ubuntu / KDE Neon)
- ✅ Raspberry Pi
- ✅ Google Colab (use `gui="nb"`)
