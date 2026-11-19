"""Audio processing demo: denoise and pitch-shift a voice or a music clip, then listen.

- **source**: switch between two signals, a synthesized singing voice and a
  music clip (``demo/audio/rabbit.mp4``, decoded with ffmpeg; a synthesized
  arpeggio when ffmpeg is not installed). ``--wav a.wav b.wav`` uses your own.
- **noise** / **snr**: corrupt it with white hiss, pink (fan-like) noise or 50 Hz mains hum.
- **denoise**: spectral gating; ``oracle noise`` gives it the true noise
  spectrum instead of estimating it from the quiet parts of the signal.
- **semitones**: pitch shift (phase vocoder), the duration is kept.
- **listen**: A/B between the clean, noisy and processed sounds, or mute (Qt and Gradio play them).
  The graph cache re-runs only the filters a slider affects: the zoom slider leaves the sound
  playing; a slider changing the sound restarts it from the beginning.

Spectrograms show what the ear hears: the noise floor, the hum lines, the harmonics moving with the pitch.

    python demo/audio_processing_demo.py            # Qt
    python demo/audio_processing_demo.py -b gradio  # in the browser
"""

import argparse
from pathlib import Path

import numpy as np

from interactive_pipe import (
    Control,
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
DURATION = 6.0
MUSIC_FILE = Path(__file__).parent / "audio" / "rabbit.mp4"

# Vowel formants (Hz) and bandwidths, an approximation of a sung "a e i o u"
VOWELS = {
    "a": ((800, 1150, 2900), (80, 90, 120)),
    "e": ((400, 2000, 2550), (70, 100, 120)),
    "i": ((300, 2300, 3000), (50, 100, 120)),
    "o": ((450, 800, 2830), (70, 80, 100)),
    "u": ((325, 700, 2530), (50, 60, 170)),
}


def synth_voice(duration=DURATION, rate=RATE):
    """A singing voice by additive synthesis: a glottal source (harmonics of f0) shaped by vowel formants.

    One note per vowel, with vibrato, a short silence between notes (useful to estimate the noise).
    """
    melody = [(220.0, "a"), (247.0, "e"), (277.0, "i"), (330.0, "o"), (294.0, "u"), (247.0, "a")]
    n = int(duration * rate)
    t = np.arange(n) / rate
    note_length = duration / len(melody)
    note = np.minimum((t / note_length).astype(int), len(melody) - 1)
    in_note = t - note * note_length
    f0 = np.array([pitch for pitch, _ in melody])[note] * (1 + 0.015 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(f0) / rate
    envelope = np.clip(in_note / 0.05, 0, 1) * np.clip((note_length - 0.15 - in_note) / 0.08, 0, 1)
    # Formant envelope per note, then harmonics of the glottal source (-12 dB/octave tilt) sampled on it
    signal = np.zeros(n)
    for harmonic in range(1, int(rate / 2 / 200)):
        frequency = harmonic * f0
        gain = np.zeros(n)
        for index, (_, vowel) in enumerate(melody):
            formants, bandwidths = VOWELS[vowel]
            mask = note == index
            resonance = sum(
                (1.0 if rank == 0 else 0.5) / (1.0 + ((frequency[mask] - f) / (1.5 * b)) ** 2)
                for rank, (f, b) in enumerate(zip(formants, bandwidths))
            )
            gain[mask] = (0.03 + resonance) / harmonic
        signal += np.where(frequency < rate / 2, gain, 0.0) * np.sin(harmonic * phase)
    breath = np.random.default_rng(1).standard_normal(n) * 0.002
    return sound.normalize((signal + breath) * envelope, 0.8)


def synth_music(duration=DURATION, rate=RATE):
    """Fallback music clip: a plucked arpeggio (A minor - F - C - G)."""
    n = int(duration * rate)
    t = np.arange(n) / rate
    chords = [(220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (261.6, 329.6, 392.0), (196.0, 246.9, 293.7)]
    step = duration / 24
    signal = np.zeros(n)
    for i in range(24):
        frequency = chords[(i // 6) % 4][i % 3] * (2 if i % 6 >= 3 else 1)
        start = int(i * step * rate)
        local = t[start:] - t[start]
        signal[start:] += np.exp(-4 * local) * sum(
            np.sin(2 * np.pi * k * frequency * local) / k**1.5 for k in range(1, 6)
        )
    return sound.normalize(signal, 0.8)


def load_sources(wav_files=None):
    """The two signals the ``source`` dropdown switches between, resampled to RATE."""
    if wav_files:
        return {
            Path(path).stem: sound.normalize(sound.load(path, RATE, duration=DURATION)[0], 0.8) for path in wav_files
        }
    try:
        music = sound.normalize(sound.load(MUSIC_FILE, RATE, start=1.0, duration=DURATION)[0], 0.8)
    except RuntimeError:  # no ffmpeg
        music = synth_music()
    return {"voice": synth_voice(), "music": music}


def make_source_picker(sources):
    """The first filter: a dropdown switching between the signals of ``sources``."""
    names = list(sources.keys())

    @interactive(source=Control(names[0], names, name="source"))
    def pick_source(source=names[0]):
        return sources[source]

    return pick_source


pick_source = make_source_picker(load_sources())


@interactive(
    noise=Control("white", ["white", "pink", "hum", "none"], name="noise", group="Noise"),
    snr=Control(5.0, [-5.0, 30.0], step=1.0, name="SNR [dB]", group="Noise"),
)
def corrupt(clean, noise="white", snr=5.0):
    if noise == "none":
        context["noise"] = None
        return clean.copy()
    noisy, noise_only = sound.add_noise(clean, snr=snr, kind=noise, sample_rate=RATE)
    context["noise"] = noise_only
    return noisy


@interactive(
    strength=Control(1.5, [0.0, 4.0], name="denoise strength", group="Denoise"),
    max_attenuation=Control(30.0, [0.0, 60.0], step=1.0, name="max attenuation [dB]", group="Denoise"),
    oracle=Control(False, name="oracle noise", group="Denoise"),
)
def remove_noise(noisy, strength=1.5, max_attenuation=30.0, oracle=False):
    noise = context.get("noise") if oracle else None
    return sound.denoise(noisy, strength=strength, max_attenuation_db=max_attenuation, noise=noise)


@interactive(semitones=Control(0.0, [-12.0, 12.0], step=1.0, name="semitones", group="Pitch"))
def shift_pitch(signal, semitones=0.0):
    return sound.pitch_shift(signal, semitones)


@interactive(listen=Control("processed", ["clean", "noisy", "processed", "mute"], name="listen"))
def play(clean, noisy, processed, listen="processed"):
    """Side effect only: send the chosen signal to the speakers."""
    if listen == "mute":
        audio.stop()
        return
    chosen = {"clean": clean, "noisy": noisy, "processed": processed}[listen]
    audio.set(np.clip(chosen, -1, 1), RATE)
    audio.play()


@interactive()
def analyse(clean, noisy, denoised, processed):
    """Spectrograms of the input and the output, SNR readouts in the titles."""
    snr_in, snr_out = sound.snr_db(clean, noisy), sound.snr_db(clean, denoised)
    layout.style("noisy_spectrogram", **sound.spectrogram_style(noisy, RATE, title=f"input  SNR {snr_in:.1f} dB"))
    layout.style(
        "output_spectrogram",
        **sound.spectrogram_style(processed, RATE, title=f"output  SNR after denoise {snr_out:.1f} dB"),
    )
    return sound.spectrogram(noisy), sound.spectrogram(processed)


@interactive(zoom_at=Control(0.5, [0.0, DURATION - 0.05], name="zoom at [s]", group="Waveform"))
def waveform(clean, processed, zoom_at=0.5):
    """40 ms of the clean and processed waveforms: the period changes with the pitch."""
    first = int(zoom_at * RATE)
    window = slice(first, first + int(0.04 * RATE))
    time_ms = 1000 * np.arange(window.start, window.stop) / RATE
    return Curve(
        [
            SingleCurve(time_ms, clean[window], style="k-", label="clean", alpha=0.6),
            SingleCurve(time_ms, processed[window], style="r-", label="processed"),
        ],
        xlabel="time [ms]",
        ylim=(-1, 1),
        grid=True,
        title="waveform",
    )


@interactive()
def average_spectrum(clean, noisy, processed):
    """Mean level per frequency: the noise floor, what the denoiser removes, where the harmonics go."""
    curves = []
    for signal, style, label in [(noisy, "c-", "noisy"), (clean, "k-", "clean"), (processed, "r-", "processed")]:
        level = 10 * np.log10(np.maximum(np.mean(10 ** (sound.spectrogram(signal) / 10), axis=1), 1e-8))[::-1]
        frequency_khz = np.linspace(0, RATE / 2000, len(level))
        curves.append(SingleCurve(frequency_khz, level, style=style, label=label, linewidth=1))
    return Curve(curves, xlabel="frequency [kHz]", ylabel="dB", ylim=(-80, 0), grid=True, title="average spectrum")


def audio_pipeline():
    clean = pick_source()
    noisy = corrupt(clean)
    denoised = remove_noise(noisy)
    processed = shift_pitch(denoised)
    play(clean, noisy, processed)
    noisy_spectrogram, output_spectrogram = analyse(clean, noisy, denoised, processed)
    zoom = waveform(clean, processed)
    spectrum = average_spectrum(clean, noisy, processed)
    return [[noisy_spectrogram, output_spectrogram], [zoom, spectrum]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Audio processing demo: denoise and pitch-shift a voice or a music clip"
    )
    parser.add_argument("-b", "--backend", choices=["qt", "gradio"], default="qt")
    parser.add_argument(
        "--wav", nargs="+", help="your own audio files (any format ffmpeg reads) instead of the two defaults"
    )
    args = parser.parse_args()
    if args.wav:
        pick_source = make_source_picker(load_sources(args.wav))  # the pipeline below picks this one up
    interactive_pipeline(gui=args.backend, name="audio processing", audio=True, cache="graph")(audio_pipeline)()
