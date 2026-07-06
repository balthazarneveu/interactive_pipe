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

- `audio.set(path)` registers the file, `audio.play()` / `audio.pause()` / `audio.stop()` control playback.
- Supported on the **Qt** backend (this is how the [Raspberry Pi jukebox](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/jukebox_demo.py) works) and on **Gradio**.
- On Gradio you can additionally return 1D numpy arrays from filters to display audio players.
- Outside a GUI (headless), the audio calls are silent no-ops, so the same filter stays batch-safe.

## API

Details: [the `audio` proxy](../api/context.md).
