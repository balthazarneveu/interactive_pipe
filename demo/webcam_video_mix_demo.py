"""
Demo: mix a video with your live webcam (and play the video's sound).

``Video`` and ``Webcam`` are two inputs of the same one-frame pipeline: the
video brings the timeline (space plays / pauses), the webcam is refreshed live.
``AudioClip`` gives the video's soundtrack the same timeline, so it plays in
sync with the frames. The webcam itself has no sound: interactive_pipe does not
record the microphone.

    python demo/webcam_video_mix_demo.py                     # built-in clip + camera
    python demo/webcam_video_mix_demo.py --video movie.mp4   # your video, with its sound (needs ffmpeg)
    python demo/webcam_video_mix_demo.py --synthetic         # no camera
"""

import argparse
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

from interactive_pipe import AudioClip, Image, Video, Webcam, interactive, interactive_pipeline

IMAGES = Path(__file__).parent / "images"
H, W = 240, 320


def demo_clip(n_frames: int = 75) -> np.ndarray:
    """``(T, H, W, 3)``: a window sliding across a photo (used without ``--video``)."""
    import cv2

    photo = cv2.resize(Image.load_image(IMAGES / "elephant.png").astype(np.float32), (2 * W, H))
    return np.stack([photo[:, k * W // n_frames :][:, :W] for k in range(n_frames)])


@interactive(mix=(0.5, [0.0, 1.0]), mode=(["cross-fade", "picture-in-picture", "difference"], "mode"))
def mix(video: np.ndarray, cam: np.ndarray, mix: float = 0.5, mode: str = "cross-fade") -> np.ndarray:
    """Combine the video frame and the camera frame (resized to the video's size)."""
    import cv2

    cam = cv2.resize(cam, (video.shape[1], video.shape[0]), interpolation=cv2.INTER_AREA)
    if mode == "difference":
        return np.clip(2.0 * np.abs(video - cam), 0.0, 1.0)
    if mode == "picture-in-picture":
        out = np.array(video)
        h, w = int(mix * video.shape[0]), int(mix * video.shape[1])
        out[-h:, -w:] = cv2.resize(cam, (w, h), interpolation=cv2.INTER_AREA)
        return out
    return (1.0 - mix) * video + mix * cam


def webcam_video_mix(video: np.ndarray, cam: np.ndarray) -> List[np.ndarray]:
    return [video, cam, mix(video, cam)]


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", help="video file (default: a built-in clip, silent)")
    parser.add_argument("--device", default="0", help="camera index, device path or stream URL")
    parser.add_argument("--synthetic", action="store_true", help="a generated scene instead of a camera")
    args = parser.parse_args(argv)

    inputs: List[Union[Video, Webcam, AudioClip]] = [Video(args.video if args.video else demo_clip(), fps=25)]
    cam = None
    if not args.synthetic:
        device = int(args.device) if args.device.isdigit() else args.device
        try:
            cam = Webcam(device, width=W, height=H).open()
        except (RuntimeError, ImportError) as exc:
            print(f"{exc}\n-> showing a generated scene instead")
    if cam is None:
        from webcam_demo import synthetic_scene

        cam = Webcam(synthetic_scene(W, H), warmup=0)
    inputs.append(cam)
    if args.video:
        try:
            inputs.append(AudioClip(args.video))  # the soundtrack, on the video's timeline
        except Exception as exc:  # no ffmpeg / no audio track
            print(f"no sound: {exc}")
    interactive_pipeline(gui="qt", cache="graph", name="Video + webcam")(webcam_video_mix)(*inputs)


if __name__ == "__main__":
    main()
