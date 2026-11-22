# Audio

Two ways to work with sound:

- **an audio input with a timeline**: call the pipeline with an `AudioClip`;
  the filters receive the whole signal, the window shows its waveform on a
  timeline, <kbd>Space</kbd> plays / pauses it ([below](#audio-inputs-and-a-timeline));
- **the `audio` proxy**: a filter plays a file or a signal it computed
  ([further down](#playing-sounds-from-filters-the-audio-proxy)).

## Audio inputs and a timeline

Write the pipeline for the **whole signal** (a numpy array) and give it an
`AudioClip`: the window gets the timeline of [video inputs](video.md), with
the waveform in place of the film strip.

```python
import numpy as np

from interactive_pipe import AudioClip, audio, interactive, interactive_pipeline, sound

RATE = 16000


@interactive(semitones=(0.0, [-12.0, 12.0]))
def shift(signal, semitones=0.0):
    return sound.pitch_shift(signal, semitones)


@interactive_pipeline(gui="qt", cache="graph")
def tune(signal):
    shifted = shift(signal)
    return shifted


t = np.arange(3 * RATE) / RATE
tune(AudioClip(0.4 * np.sin(2 * np.pi * 330 * t).astype(np.float32), RATE))
```

- `AudioClip("song.wav")` reads a file (WAV, or anything `ffmpeg` decodes:
  see `sound.load`); `sample_rate=` resamples it, `mono=False` keeps the
  channels, `start=` / `duration=` cut it. `AudioClip(signal, rate)` takes
  a numpy signal, mono `(n,)` or `(n, 2)`, float in `[-1, 1]` or `int16`.
- **What plays**: the first `AudioClip`, as it is. A filter calling
  `audio.set(signal, rate)` replaces it with what it computed, at the same
  instant, so the processed sound is heard, live, while a slider moves.
  `AudioClip(..., play=False)` keeps a clip silent.
- **The timeline (Qt)**: <kbd>Space</kbd> or ▶ plays / pauses the sound and
  the playhead follows it; click / drag on the waveform seeks, the arrows
  step (1/30 s), ⟳ loops. Dear PyGui shows the same panel without sound,
  the other backends a slider (Gradio plays the sound in its player).
- **The position**: filters read `context["timeline"]` as with a video
  (`time`, `duration`, `progress`), and
  `context["timeline"].inputs_metadata[name]` gives each clip's
  `sample_rate`, `duration` and `channels`. With `cache="graph"`, moving the
  playhead re-runs only the filters reading it (a cursor on a spectrogram,
  a zoom on the waveform), never the processing of the sound. With
  `cache=True` it re-runs nothing: the position seen by the filters only
  updates with the other changes.
- The timeline is the control named `frame` (30 per second without video):
  `tune.snapshot("/tmp/at_1s.png", clip, frame=30)`.

### Several sounds, or sounds and videos

Give several `AudioClip` inputs to mix them: they share the timeline (one
waveform lane each), which lasts as long as the longest. Load files at the
same `sample_rate` to add them sample by sample:

<!-- code: continue -->
```python
@interactive(balance=(0.5, [0.0, 1.0]))
def mix(a, b, balance=0.5):
    n = max(len(a), len(b))
    out = (1 - balance) * np.pad(a, (0, n - len(a))) + balance * np.pad(b, (0, n - len(b)))
    audio.set(out, RATE)  # the mix is what plays
    return out


@interactive_pipeline(gui="qt", cache="graph")
def blend_sounds(a, b):
    mixed = mix(a, b)
    return mixed


low = AudioClip(0.4 * np.sin(2 * np.pi * 220 * t).astype(np.float32), RATE)
high = AudioClip(0.4 * np.sin(2 * np.pi * 440 * t[: 2 * RATE]).astype(np.float32), RATE)
blend_sounds(low, high)
```

<!-- code: skip needs two sound files -->
```python
blend_sounds(AudioClip("voice.wav", sample_rate=16000), AudioClip("music.mp3", sample_rate=16000))
```

A `Video` and an `AudioClip` share the timeline too: the timeline runs at
the video frame rate, the sound plays in sync with the frames.

`demo/audio_mix_demo.py` mixes a melody and a drum loop: balance, delay,
a spectrogram with the playhead drawn on it, an oscilloscope of the 40 ms
under the playhead.

## Playing sounds from filters: the `audio` proxy

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
