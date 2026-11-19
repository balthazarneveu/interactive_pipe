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

- `audio.set(path)` registers a file; `audio.set(signal, sample_rate)` a numpy signal computed by the filter: mono `(n,)` or `(n, 2)` stereo, float in `[-1, 1]` (clipped) or `int16`. The Qt window streams signals from memory; Gradio gets a temporary WAV file, deleted when the next sound replaces it and at exit. Any other call raises `TypeError` showing both forms.
- `audio.play()` starts playback (call it after `set`); `audio.pause()` / `audio.stop()` control playback.
- **Tweaking a sound while listening (Qt)**: `audio.set(signal, rate)` continues the new version at the same sample, cross-fading over 30 ms from the previous one, in an audio thread of its own. Dragging a slider is heard live, without clicks or gaps, even when the pipeline takes ~100 ms per run (the change is heard ~0.1 s later). Play, pause and stop ramp the volume over a few ms.
- Where a new sound starts: signals keep the playback position, files (`audio.set(path)`, another track) start from the beginning; override with `keep_position=True` / `False`. `loop=True` repeats the sound (Qt). Gradio's player always starts from the beginning.
- Streaming needs Qt 6 (PyQt6 or PySide6) and an audio output; otherwise (PyQt5, no device) signals play through a temporary WAV file, restarting on each change.
- Run audio pipelines with `cache="graph"`: with the default `cache=False` every slider re-runs every filter, the one calling `audio.set` included, even for a slider that does not change the sound.

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

## Audio helpers: `interactive_pipe.sound`

Pure numpy functions (no extra dependency) for the usual steps of an audio pipeline, meant to be called inside filters. Signals are mono 1D float arrays in `[-1, 1]`.

| Function | Does |
|---|---|
| `sound.load(path, sample_rate=None, start=0, duration=None)` | `(signal, rate)` from a WAV file (standard library) or any format `ffmpeg` decodes when it is installed |
| `sound.resample(x, rate_in, rate_out)`, `sound.normalize(x, peak)`, `sound.to_mono(x)` | Basic conditioning |
| `sound.stft(x, n_fft, hop)` / `sound.istft(X, hop, length)` | Hann-window STFT, `(frames, bins)`, exact reconstruction |
| `sound.spectrogram(x)` + `sound.spectrogram_style(x, rate)` | dB heatmap (low frequencies at the bottom) and the `layout.style` arguments: colormap, dB colour bar, time / kHz axes |
| `sound.add_noise(x, snr, kind)` | `(noisy, noise)`: `"white"`, `"pink"` or `"hum"` (50 Hz mains) at a given SNR in dB |
| `sound.snr_db(reference, estimate)` | Quality readout for a title |
| `sound.denoise(x, strength, max_attenuation_db, noise=None)` | Spectral gating of stationary noise, estimated from the signal's quiet parts or from a noise sample |
| `sound.pitch_shift(x, semitones)`, `sound.time_stretch(x, factor)` | Phase vocoder: pitch without changing duration, duration without changing pitch |

```python
import numpy as np

from interactive_pipe import audio, interactive, interactive_pipeline, layout, sound

RATE = 16000


@interactive(snr=(5.0, [-5.0, 30.0]), kind=["white", "pink", "hum"])
def corrupt(clean, snr=5.0, kind="white"):
    noisy, _noise = sound.add_noise(clean, snr=snr, kind=kind, sample_rate=RATE)
    return noisy


@interactive(strength=(1.5, [0.0, 4.0]), semitones=(0.0, [-12.0, 12.0]))
def process(noisy, strength=1.5, semitones=0.0):
    out = sound.pitch_shift(sound.denoise(noisy, strength=strength), semitones)
    audio.set(out, RATE)  # Qt / Gradio play it; does nothing headless
    audio.play()
    return out


@interactive()
def show(clean, out):
    layout.style("spec", **sound.spectrogram_style(out, RATE, title=f"SNR {sound.snr_db(clean, out):.1f} dB"))
    return sound.spectrogram(out)


@interactive_pipeline(gui=None)
def denoise_and_shift(clean):
    noisy = corrupt(clean)
    out = process(noisy)
    spec = show(clean, out)
    return spec


t = np.arange(2 * RATE) / RATE
melody = 0.5 * np.sin(2 * np.pi * 220 * t * (1 + 0.5 * (t > 1)))  # two notes
(spec,) = denoise_and_shift(melody, snr=0.0)
assert spec.shape[0] == 257  # n_fft 512 -> 257 frequency rows
```

`demo/audio_processing_demo.py` is the complete app: a dropdown switches between a synthesized singing voice and a music clip, then noise, denoising, pitch shift, spectrograms of the input and the output, a zoomed waveform, the average spectrum, and a `listen` dropdown to A/B the clean, noisy and processed sounds.

## API

Details: [the `audio` proxy](../api/context.md), [the `sound` helpers](../api/sound.md).
