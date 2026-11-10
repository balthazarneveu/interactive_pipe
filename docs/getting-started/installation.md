# Installation

```bash
pip install interactive-pipe
```

The PyPI package depends on numpy, matplotlib, Pillow, PyYAML and PyQt6: the Qt backend (`gui="qt"`, the richest feature set) and the matplotlib backend work out of the box. Every other backend is an opt-in extra.

## Optional extras

| Extra | Installs | When you need it |
|---|---|---|
| `dpg` | dearpygui | The Dear PyGui backend (`gui="dpg"`), GPU-rendered window |
| `notebook` | ipywidgets | The Jupyter backend (`gui="nb"`), incl. Google Colab |
| `gradio` | gradio | The web backend (`gui="gradio"`), shareable in a browser |
| `qt5` | PyQt5 | Qt backend on systems without Qt6 support |
| `opencv` | opencv-python-headless | OpenCV as image load/save backend (Pillow is the default) |
| `pandas` | pandas | `Table` from DataFrames, csv export of tables and curves |
| `full` | Qt6 + Dear PyGui + ipywidgets + gradio + OpenCV + pandas + pytest | Everything (except PyQt5) |

```bash
pip install "interactive-pipe[dpg]"       # Dear PyGui backend
pip install "interactive-pipe[notebook]"  # Jupyter / Colab
pip install "interactive-pipe[gradio]"    # web backend
pip install "interactive-pipe[full]"      # everything
```

## Without Qt

On machines where you don't want PyQt6 (headless servers, platforms without PyQt6 wheels such as 32-bit Raspberry Pi OS), skip the dependencies of the PyPI package and install the minimal core yourself:

```bash
pip install --no-deps interactive-pipe
pip install numpy matplotlib Pillow PyYAML
```

Installing from git gives the same minimal core (no PyQt6), plus whichever extras you ask for:

```bash
pip install "interactive-pipe[notebook] @ git+https://github.com/balthazarneveu/interactive_pipe.git"
```

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
