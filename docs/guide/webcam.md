# Live webcam

Write the pipeline for **one image**, give it a **`Webcam`**: the window shows
the camera live and every slider applies to the live feed.

<!-- code: skip needs a camera -->
```python
import numpy as np

from interactive_pipe import Webcam, interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(frame, gain=1.0):
    return np.clip(frame * gain, 0.0, 1.0)


@interactive_pipeline(gui="qt")
def brighten(frame):
    bright = amplify(frame)
    return frame, bright


brighten(Webcam(0))  # the first camera, live
```

Nothing else changes: the filters still take an array (float32 RGB in
`[0, 1]`, like `Image.load_image`), and the same function called with an
image file still works.

| | Qt and Dear PyGui | matplotlib / Gradio / notebook |
|---|---|---|
| refresh | a new frame `fps` times per second (30 by default) | a new frame each time the pipeline runs (a slider moves) |
| freeze | <kbd>Space</kbd> freezes / resumes the feed; the sliders keep working on the frozen frame | – |

In the windows the camera is read in a background thread that keeps only the
latest frame: a pipeline slower than the camera skips frames, it never lags
behind or blocks the window. The thread stops when nobody asks for frames
(feed frozen, window closed) and the camera is released when Python exits.

## What a `Webcam` can be

| source | example |
|---|---|
| camera index (OpenCV) | `Webcam(0)`, `Webcam(1)` |
| device path, video stream URL | `Webcam("/dev/video2")`, `Webcam("rtsp://192.168.1.10/stream")` |
| an opened `cv2.VideoCapture` (or anything with `read() -> (ok, frame_bgr)`) | `Webcam(capture)` |
| a function returning the next frame (RGB) | `Webcam(sdk_camera.grab)`, `Webcam(simulation_step)` |
| an iterator / generator of frames (RGB) | `Webcam(frames_generator())`, `Webcam(iter(frame_list))` |

Options:

- `width=`, `height=`: resolution asked to the camera (it picks the closest it has)
- `fps=`: refresh rate of the window, also asked to the camera (default 30)
- `mirror=True`: flip left / right, like a video call shows yourself
- `as_float=False`: hand the uint8 frames over as they are
- `warmup=`: frames dropped when the camera opens (3 by default: the first
  ones are often dark while the auto exposure settles)
- `freeze_key=`: the freeze key (space by default)

A function source returns `None` when it has no new frame: the previous one
is shown again. An iterator that is exhausted behaves the same way: the last
frame stays on screen.

## Without a window

Headless runs, snapshots and sweeps read **one new frame per run**:

```python
import numpy as np

from interactive_pipe import Webcam, interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(frame, gain=1.0):
    return np.clip(frame * gain, 0.0, 1.0)


@interactive_pipeline(gui="qt")
def brighten(frame):
    bright = amplify(frame)
    return frame, bright


rng = np.random.default_rng(0)
camera = Webcam(lambda: rng.uniform(size=(48, 64, 3)))  # stands for Webcam(0) here
frame, bright = brighten.headless(camera, gain=1.5)  # grab a frame, process it
brighten.snapshot("/tmp/webcam.png", camera, gain=1.5)  # what the window would show
```

To process the same frame with several settings (a sweep, a test), grab it
once and give the array: `frame = camera.read()`, then
`brighten.sweep("/tmp/gains.png", frame, gain=[0.5, 1, 2])`.

`camera.read()` reads a frame now; `camera.release()` closes the camera (it
opens again at the next frame); `with Webcam(0) as camera:` does both.
`Webcam(0).open()` opens it right away and raises `RuntimeError` when there
is no camera at that index (or another program uses it): a script can fall
back to something else, like `demo/webcam_demo.py` does.

## How it works

Like a [`Video`](video.md), a `Webcam` input gets a small filter in front of
the others (`webcam_<input name>`, shown by `describe()`) that writes the
latest frame in place of the input. A clock control named **`live`** (a
`TimeControl` without a widget) drives it: each tick of the window timer
shows a new frame, and its pause key is the freeze. The frame filter is never
served from the cache, so everything after it runs on each new frame; with
`cache="graph"` a branch that does not read the frame is not recomputed.

## Example

`demo/webcam_demo.py`: a cartoon effect (posterized colours and an edge map)
tuned live on the camera. `--synthetic` uses a generated scene instead.
