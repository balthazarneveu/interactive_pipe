"""
Demo: a video plus a dedicated sound (a drum loop), mixed on one timeline.

``Video`` and ``AudioClip`` inputs share the timeline: space plays the frames
and the sound together. ``mix`` balances the video's own soundtrack with the
drums (what plays is set with ``audio.set``) and ``pulse`` makes the picture
flash with the drums at the playhead.

    python demo/video_sound_mix_demo.py                     # built-in clip (silent) + synthesized drums
    python demo/video_sound_mix_demo.py --video movie.mp4   # its soundtrack too (needs ffmpeg)
    python demo/video_sound_mix_demo.py --drums beat.wav    # your own sound
"""

import argparse
from pathlib import Path
from typing import List

import numpy as np

from interactive_pipe import AudioClip, Image, Video, audio, context, interactive, interactive_pipeline, layout

IMAGES = Path(__file__).parent / "images"
RATE = 16000
SIZE = 240


def demo_clip(n_frames: int = 75) -> np.ndarray:
    """``(T, SIZE, SIZE, 3)``: a window sliding across a photo (3 s at 25 fps)."""
    import cv2

    photo = cv2.resize(Image.load_image(IMAGES / "elephant.png").astype(np.float32), (2 * SIZE, SIZE))
    return np.stack([photo[:, k * SIZE // n_frames :][:, :SIZE] for k in range(n_frames)])


def drum_loop(duration: float = 4.0) -> np.ndarray:
    """A kick on every beat and a hi-hat in between (120 bpm)."""
    t = np.arange(int(duration * RATE)) / RATE
    beat = t % 0.5
    kick: np.ndarray = np.sin(2 * np.pi * 55 * beat * (1 + 2 * np.exp(-beat * 30))) * np.exp(-beat * 12)
    off = (t + 0.25) % 0.5
    hat = np.random.default_rng(0).standard_normal(len(t)) * np.exp(-off * 60) * 0.3
    return (0.7 * kick + hat).astype(np.float32)


@interactive(balance=(0.7, [0.0, 1.0], "video sound ↔ drums"), delay=(0.0, [0.0, 2.0], "drums delay [s]"))
def mix(soundtrack: np.ndarray, drums: np.ndarray, balance: float = 0.7, delay: float = 0.0) -> np.ndarray:
    """Weighted sum of the video's soundtrack and the drums; this is what plays."""
    shift = int(delay * RATE)
    out = np.zeros(max(len(soundtrack), shift + len(drums)), np.float32)
    out[: len(soundtrack)] += (1.0 - balance) * soundtrack
    out[shift : shift + len(drums)] += balance * drums
    out = np.clip(out, -1.0, 1.0)
    audio.set(out, RATE)
    return out


@interactive(strength=(0.6, [0.0, 1.0], "flash"))
def pulse(frame: np.ndarray, mixed: np.ndarray, strength: float = 0.6) -> np.ndarray:
    """Brighten the frame with the sound level at the playhead (only this re-runs while playing)."""
    start = int(context["timeline"].time * RATE)
    level = float(np.abs(mixed[start : start + int(0.05 * RATE)]).max(initial=0.0))
    layout.style("flashing", title=f"level {level:.2f}")
    return np.clip(frame * (1.0 + strength * 2.0 * level), 0.0, 1.0)


def video_with_sound(frame: np.ndarray, soundtrack: np.ndarray, drums: np.ndarray) -> List[np.ndarray]:
    mixed = mix(soundtrack, drums)
    flashing = pulse(frame, mixed)
    return [frame, flashing]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", help="video file (default: a built-in silent clip)")
    parser.add_argument("--drums", help="sound file instead of the synthesized drums")
    args = parser.parse_args()
    video = Video(args.video if args.video else demo_clip(), fps=25)
    if args.video:
        soundtrack = AudioClip(args.video, sample_rate=RATE, play=False, description="soundtrack")
    else:
        soundtrack = AudioClip(np.zeros(3 * RATE, np.float32), RATE, play=False, description="soundtrack (silent)")
    drums = AudioClip(args.drums, sample_rate=RATE) if args.drums else AudioClip(drum_loop(), RATE, description="drums")
    interactive_pipeline(gui="qt", cache="graph", name="Video + sound")(video_with_sound)(video, soundtrack, drums)
