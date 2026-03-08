# GUI Backends

Interactive Pipe supports multiple GUI backends, each with different features and use cases.

## Available Backends

| Backend | Description | Use Case |
|---------|-------------|----------|
| `qt` | PyQt/PySide | Desktop applications, full features |
| `mpl` | Matplotlib | Scientific visualization |
| `nb` | IPywidgets | Jupyter notebooks, Google Colab |
| `gradio` | Gradio | Web apps, sharing with others |

## Selecting a Backend

Specify the backend when decorating your pipeline:

```python
from interactive_pipe import interactive_pipeline

# Qt backend
@interactive_pipeline(gui="qt")
def my_pipeline(img):
    return processed_img

# Matplotlib backend
@interactive_pipeline(gui="mpl")
def my_pipeline(img):
    return processed_img

# Jupyter notebook backend
@interactive_pipeline(gui="nb")
def my_pipeline(img):
    return processed_img

# Gradio backend (can share online)
@interactive_pipeline(gui="gradio", share_gradio_app=True)
def my_pipeline(img):
    return processed_img
```

## Feature Comparison

| Feature | Qt | Matplotlib | Jupyter | Gradio |
|:-----:|:-----:|:------:|:----: |:----: |
| Backend name | `qt` | `mpl` | `nb` | `gradio` |
| Plot curves | ✅ | ✅ | ✅ | ✅ |
| Auto refreshed layout | ✅ | ✅ | ✅ | ➖ |
| Keyboard shortcuts / fullscreen | ✅ | ✅ | ➖ | ➖ |
| Audio support | ✅ | ➖ | ➖ | ✅ |
| Image buttons | ✅ | ➖ | ➖ | ➖ |
| Circular slider | ✅ | ➖ | ➖ | ➖ |

## Qt Backend

**Preview:**

![qt backend](/doc/images/qt_backend.jpg)

**Features:**
- Full keyboard shortcut support
- Fullscreen mode (F11)
- Audio playback
- Image buttons
- Circular sliders
- Most feature-complete backend

**Installation:**

```bash
pip install interactive-pipe[qt]
# or
pip install interactive-pipe PySide6
# or
pip install interactive-pipe PyQt5
```

## Matplotlib Backend

**Preview:**

![mpl backend](/doc/images/mpl_backend.jpg)

**Features:**
- Great for scientific visualization
- Keyboard shortcuts
- Curve plotting
- No audio support

**Installation:**

```bash
pip install interactive-pipe[mpl]
# or
pip install interactive-pipe matplotlib
```

## Jupyter Notebook Backend

**Preview:**

![nb backend](/doc/images/notebook_backend.jpg)

**Features:**
- Works in Jupyter notebooks
- Works on Google Colab
- Sliders added automatically
- No keyboard shortcuts

**Installation:**

```bash
pip install interactive-pipe[nb]
# or
pip install interactive-pipe ipywidgets
```

**Usage in notebooks:**

```python
from interactive_pipe import interactive, interactive_pipeline
import numpy as np

@interactive()
def process(img, brightness=(1.0, [0.5, 2.0])):
    return img * brightness

@interactive_pipeline(gui="nb")
def pipeline(img):
    return process(img)

# Run in notebook cell
img = np.random.rand(256, 256, 3)
pipeline(img)
```

## Gradio Backend

**Preview:**

![gradio backend](/doc/images/gradio_backend.jpg)

**Features:**
- Web-based interface
- Share your app with others (when using `share_gradio_app=True`)
- Audio support
- Great for demos and prototypes
- Experimental (🧪)

**Installation:**

```bash
pip install interactive-pipe[gradio]
# or
pip install interactive-pipe gradio
```

**Sharing your app:**

```python
@interactive_pipeline(gui="gradio", share_gradio_app=True)
def pipeline(img):
    return processed_img

# This will generate a public URL you can share
pipeline(img)
```

## Window Size Options

Control the window size for Qt and Matplotlib backends:

```python
# Specific size
@interactive_pipeline(gui="qt", size=(1024, 768))
def pipeline(img):
    return img

# Fullscreen
@interactive_pipeline(gui="qt", size="fullscreen")
def pipeline(img):
    return img

# Maximized (Qt only)
@interactive_pipeline(gui="qt", size="maximized")
def pipeline(img):
    return img
```

## Backend Compatibility Notes

### KeyboardControl

KeyboardControls work in Qt and Matplotlib backends. When using notebook or Gradio backends, they automatically fall back to regular sliders.

```python
# This works in all backends
@interactive()
def switch_mode(img, mode=(0, [0, 2], None, ["pagedown", "pageup"])):
    # Keyboard shortcuts in Qt/mpl, regular slider in nb/gradio
    return apply_mode(img, mode)
```

### Audio Playback

Audio is only supported in Qt and Gradio backends:

```python
from interactive_pipe import audio

@interactive()
def process_audio(audio_signal):
    # Process the audio
    processed = apply_effects(audio_signal)
    
    # Play it (Qt and Gradio only)
    audio.set_audio("output.wav")
    
    return processed
```

## Testing Platforms

- ✅ Linux (Ubuntu / KDE Neon)
- ✅ Raspberry Pi
- ✅ Google Colab (use `gui='nb'`)
- ✅ Windows (Qt, Matplotlib)
- ✅ macOS (Qt, Matplotlib)
