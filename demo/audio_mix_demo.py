"""
Demo: mix two sounds on a timeline, hear the mix and watch it follow the playhead.

Two ``AudioClip`` inputs share the timeline (one waveform lane each). The
filters receive the whole signals:

- ``mix``: balance the melody and the drum loop, delay the drums; the mix is
  what plays (``audio.set``). Moving a slider is heard live, at the same instant.
- ``spectrogram`` of the mix (recomputed only when the mix changes) and a
  ``cursor`` drawn on it at the playhead (``context["timeline"].time``);
- ``scope``: the 40 ms of the mix under the playhead, an oscilloscope.

<kbd>Space</kbd> plays / pauses the sound and the playhead follows it;
click on the waveforms to seek. ``cache="graph"`` re-runs only what a change
affects: while playing, only the cursor and the scope.

    python demo/audio_mix_demo.py                       # synthesized melody and drums
    python demo/audio_mix_demo.py --files a.wav b.mp3   # your own sounds (mp3 & co need ffmpeg)
"""

import argparse
from typing import List, Union

import numpy as np

from interactive_pipe import (
    AudioClip,
    Curve,
    SingleCurve,
    audio,
    context,
    interactive,
    interactive_pipeline,
    layout,
    sound,
)

RATE = 16000


def melody(duration: float = 6.0) -> np.ndarray:
    """A plucked arpeggio: decaying harmonics, one note every 0.375 s."""
    notes = [220.0, 277.2, 329.6, 440.0, 329.6, 277.2]
    t = np.arange(int(duration * RATE)) / RATE
    step = 0.375
    index = (t // step).astype(int) % len(notes)
    f0 = np.array(notes)[index]
    local = t % step
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    tone = sum(np.sin(k * phase) / k for k in (1, 2, 3, 4))
    return (0.35 * tone * np.exp(-local * 6.0)).astype(np.float32)


def drums(duration: float = 4.0) -> np.ndarray:
    """A kick on every beat and a hi-hat in between (120 bpm), shorter than the melody."""
    t = np.arange(int(duration * RATE)) / RATE
    beat = t % 0.5
    kick = np.sin(2 * np.pi * 55 * beat * (1 + 2 * np.exp(-beat * 30))) * np.exp(-beat * 12)
    off = (t + 0.25) % 0.5
    hat = np.random.default_rng(0).standard_normal(len(t)) * np.exp(-off * 60) * 0.3
    return (0.7 * kick + hat).astype(np.float32)


@interactive(
    balance=(0.5, [0.0, 1.0], "melody ↔ drums"),
    delay=(0.0, [0.0, 2.0], "drums delay [s]"),
)
def mix(melody: np.ndarray, drums: np.ndarray, balance: float = 0.5, delay: float = 0.0) -> np.ndarray:
    """Weighted sum of the two sounds, the drums starting ``delay`` seconds later; this is what plays."""
    shift = int(delay * RATE)
    length = max(len(melody), shift + len(drums))
    out = np.zeros(length, np.float32)
    out[: len(melody)] += (1.0 - balance) * melody
    out[shift : shift + len(drums)] += balance * drums
    out = np.clip(out, -1.0, 1.0)
    audio.set(out, RATE)  # replaces the first clip as the sound playing, at the same instant
    return out


@interactive()
def spectrogram(mixed: np.ndarray) -> np.ndarray:
    return sound.spectrogram(mixed)


@interactive()
def cursor(spec: np.ndarray, mixed: np.ndarray) -> np.ndarray:
    """The spectrogram with a line at the playhead (only this re-runs while playing)."""
    timeline = context["timeline"]
    out = np.array(spec)
    column = int(timeline.time / (len(mixed) / RATE) * (out.shape[1] - 1))
    out[:, max(column - 1, 0) : column + 1] = 0.0  # 0 dB: the brightest colour
    layout.style("marked", **sound.spectrogram_style(mixed, RATE, title=f"mix · {timeline}"))
    return out


@interactive()
def scope(mixed: np.ndarray) -> Curve:
    """The 40 ms of the mix under the playhead."""
    start = int(context["timeline"].time * RATE)
    window = mixed[start : start + int(0.04 * RATE)]
    time_ms = 1000 * np.arange(len(window)) / RATE
    return Curve([SingleCurve(x=time_ms, y=window)], ylim=(-1, 1), xlabel="ms", title="under the playhead")


def mix_two_sounds(melody: np.ndarray, drums: np.ndarray) -> List[Union[np.ndarray, Curve]]:
    mixed = mix(melody, drums)
    spec = spectrogram(mixed)
    marked = cursor(spec, mixed)
    zoom = scope(mixed)
    return [marked, zoom]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mix two sounds on a timeline")
    parser.add_argument("-b", "--backend", choices=["qt", "dpg", "gradio", "mpl"], default="qt")
    parser.add_argument("--files", nargs=2, metavar=("FIRST", "SECOND"), help="two sound files instead")
    args = parser.parse_args()
    if args.files:
        first, second = (AudioClip(path, sample_rate=RATE) for path in args.files)  # one rate to mix them
    else:
        first, second = AudioClip(melody(), RATE, description="melody"), AudioClip(drums(), RATE, description="drums")
    interactive_pipeline(gui=args.backend, cache="graph", name="Mix two sounds")(mix_two_sounds)(first, second)
