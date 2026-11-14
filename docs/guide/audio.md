# Audio

Audio is not returned from filters — it is driven by the `audio` proxy as a side effect, typically reacting to a control:

```python
from interactive_pipe import audio, interactive


@interactive(song=(["silence", "elephant", "snail"]))
def choose_song(img, song="silence"):
    if song == "silence":
        audio.stop()
    else:
        audio.set(f"tracks/{song}.mp4")
        audio.play()
    return img
```

- `audio.set(path)` registers a file; `audio.set(signal, sample_rate)` a numpy signal computed by the filter: mono `(n,)` or `(n, 2)` stereo, float in `[-1, 1]` (clipped) or `int16`. The library writes it to a temporary WAV, deleted when the next sound replaces it and at exit. Any other call raises `TypeError` showing both forms.
- `audio.play()` starts playback (call it after `set`); each `set` stops the current sound and loads the new one from its start, so a filter calling `set` then `play` restarts the sound whenever a slider changes its output. `audio.pause()` / `audio.stop()` control playback.

```python
import numpy as np

from interactive_pipe import audio, interactive

RATE = 16000


@interactive(pitch=(440.0, [110.0, 880.0]))
def tone(pitch=440.0):
    t = np.arange(RATE) / RATE
    signal = 0.3 * np.sin(2 * np.pi * pitch * t)
    audio.set(signal, RATE)
    audio.play()
    return signal  # also shown as a curve
```

- Supported on the **Qt** backend (this is how the [Raspberry Pi jukebox](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox_demo.py) works) and on **Gradio**; not available on matplotlib, notebook or Dear PyGui.
- On Gradio you can additionally return 1D numpy arrays from filters to display audio players.
- Outside a GUI (headless, snapshots, sweeps, tests), the audio calls check their arguments and do nothing else: no file, no audio device, so the same filter stays batch-safe.

## API

Details: [the `audio` proxy](../api/context.md).
