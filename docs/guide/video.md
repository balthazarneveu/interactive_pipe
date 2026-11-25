# Video inputs & timeline

Write the pipeline for **one frame**, give it a **`Video`**: the window gets a
timeline at the bottom (film strip, play / pause, step, timecode) and every
filter receives the frame under the playhead.

![Qt window with a video timeline](../images/video_timeline.png)

```python
import numpy as np

from interactive_pipe import Video, interactive, interactive_pipeline


@interactive(gain=(1.0, [0.0, 2.0]))
def amplify(frame, gain=1.0):
    return np.clip(frame * gain, 0.0, 1.0)


@interactive_pipeline(gui="qt")
def brighten(frame):
    bright = amplify(frame)
    return frame, bright


frames = np.random.default_rng(0).uniform(size=(50, 64, 96, 3)).astype(np.float32)
brighten(Video(frames, fps=25))  # a window with a timeline
```

Nothing else changes: the filters still take an array, the sliders still
apply to what is on screen, and the same function called with a plain image
still works without a timeline.

## What a `Video` can be made from

| source | example |
|---|---|
| video file (OpenCV; `.gif` also with Pillow only) | `Video("clip.mp4")` |
| folder of images, glob pattern, list of paths | `Video("frames/")`, `Video("shots/*.png")` |
| numpy array `(T, H, W)` / `(T, H, W, C)`, list of arrays | `Video(stack, fps=30)` |
| torch tensor `(T, C, H, W)` / `(T, H, W, C)`, list of tensors | `Video(tensor)` |
| iterator / generator of frames, opened `cv2.VideoCapture` | `Video(simulate(), max_frames=200)` |
| any file format: folder / pattern / paths and a `loader` | `Video("raw/*.dng", loader=read_dng)` |
| a `FrameSource` subclass, any lazy sequence (`len` + `[i]`) | `Video(RawBurst("capture.bin"))`, `Video(dataset)` |

Files and image folders are decoded lazily (only the frames you visit, the
last ones kept in a small cache), as `[0, 1]` float RGB like `Image.load_image`.
Arrays and tensors are handed over as they are. Torch frames become numpy
`(H, W[, C])` arrays unless you pass `to_numpy=False`, which hands the tensor
slices to your model filter (see `demo/video_compare_demo.py`).

Other options: `fps=` (default: the file's, else 25), `start=`, `stop=`,
`step=` (keep `frames[start:stop:step]`), `max_frames=` for streams,
`timeline=` ([below](#showing-folding-or-hiding-it)), `preview=`
([below](#custom-formats-and-per-frame-metadata)), `preload=`,
`thumbnail_loader=` and `cache_frames=`
([below](#read-ahead-and-thumbnails)).

## The timeline

| | Qt and Dear PyGui | matplotlib / Gradio / notebook |
|---|---|---|
| widget | a panel at the bottom: transport and timecode, then a full-width film strip | frame slider |
| play / pause | <kbd>Space</kbd> or ▶ | – |
| step one frame | <kbd>←</kbd> <kbd>→</kbd> or ‹ › | slider |
| seek | click / drag on the strip | slider |
| zoom | scroll on the strip (shift + scroll pans, double-click shows it all) | – |

Playback runs at the video frame rate. When the pipeline is slower than the
video, frames are skipped like a player does (the display never lags behind).
The ⟳ button toggles looping. Zoomed in, the strip shows the frames one by
one, a thin bar under it shows which part of the video is visible, and the
view follows the playhead during playback. A `KeyboardControl` or a context
event already bound to space or the arrows keeps them.

### Showing, folding or hiding it

`Video(..., timeline=...)` chooses how the Qt and Dear PyGui windows show
the timeline (the first `Video` input decides):

| `timeline=` | |
|---|---|
| `"shown"` (default) | the whole panel |
| `"collapsible"` | a ⌄ button on the right folds the panel to its transport row, giving the room back to the images |
| `"collapsed"` | collapsible, folded at start |
| `"hidden"` | no panel: <kbd>Space</kbd> and <kbd>←</kbd> <kbd>→</kbd> still play and step |

<!-- code: continue -->
```python
brighten(Video(frames, fps=25, timeline="hidden"))  # keyboard only
```

The panel takes the window's light or dark look on Qt (Dear PyGui is dark).

The timeline is an ordinary control named **`frame`**: the call can set the
starting frame, and snapshots, sweeps, tuning files and sessions see it too.

<!-- code: continue -->
```python
clip = Video(frames, fps=25)
brighten(clip, frame=20)  # opens at frame 20
brighten.headless(clip, frame=10, gain=1.5)  # outputs at frame 10, no window
brighten.snapshot("/tmp/frame10.png", clip, frame=10)
brighten.sweep("/tmp/contact_sheet.png", clip, frame=[0, 10, 20, 30, 40])
```

`export_animation` renders the whole video, at its frame rate, when the
pipeline has a `Video` input. Press <kbd>V</kbd> in the window to do the same.

<!-- code: continue -->
```python
from interactive_pipe import export_animation

export_animation(brighten.headless, "/tmp/brighten.gif", output=1)  # the second output
```

## Reading the position in a filter

Filters read the timeline position from the context: `context["timeline"]`
is a `Timeline` with `frame`, `time` (seconds), `fps`, `n_frames`,
`duration`, `progress` (0 to 1) and the `metadata` of the frame
([custom formats](#custom-formats-and-per-frame-metadata)). Printed, it
reads `00:01.20 / 00:04.00 · frame 30/99`.

```python
import numpy as np

from interactive_pipe import Video, context, interactive, interactive_pipeline, layout


@interactive()
def fade_in(frame):
    timeline = context["timeline"]
    layout.style("faded", title=str(timeline))
    return frame * min(timeline.time / 1.0, 1.0)  # 1 s fade from black


@interactive_pipeline(gui="qt")
def fading(frame):
    faded = fade_in(frame)
    return faded


fading(Video(np.ones((50, 32, 32, 3), np.float32), fps=25))
```

## Several videos, one timeline

Give several `Video` inputs: they share the timeline, and every filter
receives the frame of each video at the current time. Blending two clips is
an ordinary filter with two inputs:

```python
import numpy as np

from interactive_pipe import Video, interactive, interactive_pipeline


@interactive(mix=(0.5, [0.0, 1.0]))
def cross_fade(a, b, mix=0.5):
    return (1.0 - mix) * a + mix * b


@interactive_pipeline(gui="qt")
def blend(a, b):
    mixed = cross_fade(a, b)
    return a, mixed, b


rng = np.random.default_rng(0)
first = Video(rng.uniform(size=(75, 48, 64, 3)).astype(np.float32), fps=25)  # 3 s
second = Video(np.ones((24, 48, 64, 3), np.float32), fps=12)  # 2 s
blend(first, second, frame=30)
```

- The film strip shows **one lane per input**, labelled with the input name,
  under one playhead.
- When the frame rates differ, each video shows the frame matching the
  current *time*: the timeline runs at the first video's frame rate and
  lasts as long as the longest one.
- A shorter video holds its last frame after its end; its lane stops there.
- The frames are handed over as they are: resize them in a filter when the
  videos differ in size.
- An `AudioClip` input joins the same timeline with a waveform lane, and
  plays in sync with the frames ([audio inputs](audio.md#audio-inputs-and-a-timeline)).

<!-- code: skip needs two video files -->
```python
compare(Video("reference.mp4"), Video("encoded_15fps.mp4"))
```

## A video made by a filter

A filter may also *return* a `Video`: a burst it simulates, frames it
renders from its sliders, a clip it loads from a path chosen in a menu. The
window gets the same timeline as for a `Video` input, and the filters after
it receive the frame under the playhead:

```python
import numpy as np

from interactive_pipe import Video, context, interactive, interactive_pipeline, layout


@interactive(n=(24, [2, 60]), speed=(1.0, [0.1, 4.0]), fps=(12.0, [1.0, 30.0]))
def orbit(n=24, speed=1.0, fps=12.0):
    """A dot circling the frame, one frame per step."""
    yy, xx = np.mgrid[:64, :64]
    frames = []
    for k in range(n):
        angle = 2 * np.pi * speed * k / n
        cx, cy = 32 + 20 * np.cos(angle), 32 + 20 * np.sin(angle)
        dot = ((xx - cx) ** 2 + (yy - cy) ** 2 < 25).astype(np.float32)
        frames.append(np.stack([dot] * 3, axis=-1))
    return Video(np.stack(frames), fps=fps)


def label(frame):
    timeline = context["timeline"]
    layout.style("shown", title=f"frame {timeline.frame} / {timeline.n_frames}")
    return frame


@interactive_pipeline(gui="qt", cache="graph")
def generated():
    clip = orbit()
    shown = label(clip)
    return shown


generated()
```

- The timeline appears after the first run, when the filter has returned its
  video. Its length and frame rate follow the video: change `n` and the film
  strip is rebuilt, the playhead clamped to the new end.
- Moving the playhead never runs the filter making the video again (with
  `cache=True` or `"graph"`): only what follows the frame.
- A filter that returns a `Video` sometimes and an image other times works:
  the image goes through as it is.
- With `Video` inputs too, all of them share one timeline, one lane each.
- Qt and Dear PyGui show the timeline. Headless runs and `snapshot` show the
  frame under the playhead (the first one by default); `frame=` at the call
  only applies to `Video` inputs.

## Temporal filters: `window=`

A filter that needs the past (frame differences, temporal denoising, motion)
takes a `Video(..., window=k)`: it receives the `k` frames ending at the
current one, stacked on a first axis `(k, H, W[, C])` (at the start of the
video the first frame is repeated). Give the same frames twice to get both
the current frame and the window:

```python
import numpy as np

from interactive_pipe import Video, interactive, interactive_pipeline


@interactive(threshold=(0.1, [0.0, 0.5]))
def motion(frames, threshold=0.1):
    return (np.abs(frames[-1] - frames[0]).max(axis=-1) > threshold).astype(np.float32)


@interactive_pipeline(gui="qt")
def detect(frame, frames):
    mask = motion(frames)
    return frame, mask


stack = np.random.default_rng(0).uniform(size=(30, 48, 64, 3)).astype(np.float32)
detect(Video(stack), Video(stack, window=3), frame=10)
```

`clip.with_window(3)` is the same video (sharing its decoded frames) with a
window.

## Custom formats and per-frame metadata

### One file per frame: `loader=`

A sequence of files in a format `Video` does not read (DNG, EXR, a lab's own
raw format...) takes a `loader`: a function called with each path. It
returns the frame, or `(frame, metadata)` when the file also tells
something about the shot. Give a glob pattern, a folder (every file in it)
or a list of paths:

<!-- code: skip needs rawpy and DNG files -->
```python
import rawpy


def read_dng(path):
    with rawpy.imread(str(path)) as raw:
        mosaic = raw.raw_image_visible.astype(np.float32)
        return mosaic, {"white_balance": raw.camera_whitebalance, "black_level": raw.black_level_per_channel}


develop(Video("shoot/*.dng", loader=read_dng, preview=lambda mosaic: mosaic / 16383))
```

Files are still read lazily, only when the timeline reaches them.

### Anything else: `FrameSource`

For a file holding many frames, a camera SDK or frames computed on demand,
subclass `FrameSource`: `__len__` and `read(index)`, and optionally
`metadata(index)`, `fps` and `description`. The `Video` reads the frames
lazily and caches them. Any object with `len()` and `[index]` (a torch
`Dataset`...) also works as it is, and its items may be `(frame, metadata)`.

```python
import numpy as np

from interactive_pipe import FrameSource, Video


class Simulation(FrameSource):
    fps = 30.0
    description = "heat diffusion"

    def __len__(self):
        return 100

    def read(self, index):
        return np.full((32, 32), index / 100, np.float32)

    def metadata(self, index):
        return {"temperature": 20 + index / 10}


clip = Video(Simulation())
print(clip, clip.metadata(50))  # Video(heat diffusion, 100 frames, 30 fps) {'temperature': 25.0}
```

### Reading the metadata in a filter

`context["timeline"].metadata` is the metadata of the frame on screen
(of the first `Video` input; `context["timeline"].inputs_metadata` has every
input's, by input name). Frames read from files also give their `"path"`.
`clip.metadata(index)` reads it outside a pipeline.

<!-- code: continue -->
```python
from interactive_pipe import context, interactive, interactive_pipeline, layout


@interactive()
def thermometer(frame):
    temperature = context["timeline"].metadata["temperature"]
    layout.style("heat", title=f"{temperature:.1f} °C")
    return frame


@interactive_pipeline(gui="qt")
def watch(frame):
    heat = thermometer(frame)
    return heat


watch.headless(clip, frame=30)
```

`preview=` gives the film strip thumbnails of frames that are not images to
look at as they are (a raw mosaic, 10-bit data): a function frame → image.
The filters still receive the frames unchanged.

## Read-ahead and thumbnails

The Qt and Dear PyGui windows work in the background like an editing
software, so a slow decoder (RAW files, a large video, a network drive) does
not freeze the window:

- **Read-ahead.** Whenever the playhead moves, the next `preload` frames
  (8 by default) are decoded in a background thread, so playback finds
  them ready. A thin band along the bottom of the ruler, after the playhead,
  shows the frames in memory. `preload=0` turns it off; the frame cache
  (`cache_frames=`, 32 by default) grows to hold the frames ahead.
  `export_animation` reads ahead too.
- **Thumbnails.** The film strip draws grey tiles and fills them in as the
  thumbnails are built in the background, nearest the playhead first. They
  do not take room in the frame cache.

Read-ahead speeds up decoding only: when the filters are the slow part,
playback still skips frames to keep up. The background thread exists only
while a window asks for frames, and stops after two idle seconds: headless
pipelines, snapshots and tests never start one.

### Cheap thumbnails

A thumbnail is made from the decoded frame by default (through `preview=`).
When your format has something cheaper (the JPEG embedded in a DNG, a
low-resolution level, a sidecar preview file), hand it over instead and
the strip never decodes the full frames:

<!-- code: skip needs rawpy and DNG files -->
```python
import io

from PIL import Image


def dng_preview(path):
    with rawpy.imread(str(path)) as raw:
        return np.asarray(Image.open(io.BytesIO(raw.extract_thumb().data)))  # the embedded JPEG


develop(Video("shoot/*.dng", loader=read_dng, thumbnail_loader=dng_preview))
```

A `FrameSource` gets the same with a `thumbnail(index)` method:

<!-- code: continue -->
```python
class SimulationWithPreview(Simulation):
    def thumbnail(self, index):
        return np.full((8, 8), index / 100, np.float32)  # any size: resized to the strip


clip = Video(SimulationWithPreview())
print(clip.thumbnail(50, height=16).shape)  # (16, 16, 3)
```

A thumbnail is any image shown as it is (uint8, or floats in `[0, 1]`);
`preview=` does not apply to it. `read` and `thumbnail` may be called from
the background thread, never two at a time, so a reader needs no lock.

## How it works

When an input is a `Video`, the pipeline puts a small filter in front of the
others (`video_<input name>`, shown by `describe()` and the graph) that reads
the frame from the `Video` and writes it in place of the input. A
`TimelineControl` drives that filter. So the cache recomputes only what
follows the frame when the playhead moves (use `cache=True` or `"graph"` so
slider changes do not decode the frame again), and every tool that knows
controls knows the timeline.

A filter returning a `Video` gets the same treatment, made during the run:
right after the filter has run, a `video_<output name>` filter is put after it
and the timeline is created (or resized) from the video.

## Examples

- `demo/video_grading_demo.py`: grade a video file (exposure, saturation,
  white balance) with a histogram. The title shows the timecode.
- `demo/video_motion_demo.py`: motion detection on a numpy simulation with
  `window=3`, with boxes drawn on the moving objects.
- `demo/video_blend_demo.py`: two clips of different lengths and frame
  rates blended four ways (cross-fade, a dissolve following the playhead,
  difference, wipe), one lane each on the film strip.
- `demo/video_compare_demo.py`: a restoration model fed with torch tensors
  at 12 fps, compared with a 24 fps reference: wipe, error map, PSNR.
- `demo/video_raw_sequence_demo.py`: a RAW burst in a custom file format read
  with `loader=`; the filters use each shot's exposure, ISO and white balance
  (`context["timeline"].metadata`) to remove the auto-exposure flicker.
