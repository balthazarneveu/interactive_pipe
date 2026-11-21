"""``Webcam``: a live camera feed given to a pipeline as one input.

The pipeline function is written for a single frame; the pipeline puts a small
frame filter in front of the others and a ``LiveControl`` clock that refreshes
it (see ``interactive_pipe.headless.live`` and ``docs/guide/webcam.md``).

Sources:

- a camera index (``Webcam(0)``) or a device path / stream URL
  (``"/dev/video2"``, ``"rtsp://..."``), opened with OpenCV
- an opened ``cv2.VideoCapture`` (or anything with ``read() -> (ok, frame_bgr)``)
- a function returning the next frame (a camera SDK, a simulation, a test)

In a window the camera is read in a background thread that keeps only the
latest frame, so a slow pipeline never shows an old frame and never blocks on
the camera. Headless (``pipe.headless``, ``snapshot``) every run reads a new
frame directly.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
import weakref
from typing import Any, Callable, Optional, Union

import numpy as np

DEFAULT_LIVE_FPS = 30.0
#: frames read and dropped when a camera opens (auto exposure / white balance settling)
DEFAULT_WARMUP_FRAMES = 3
#: seconds the background reader keeps going without anyone asking for a frame
READER_IDLE_SECONDS = 2.0
#: seconds to wait for the first frame of a camera before giving up
FIRST_FRAME_TIMEOUT = 5.0

_open_webcams: "weakref.WeakSet[Webcam]" = weakref.WeakSet()


@atexit.register
def _release_all() -> None:
    for webcam in list(_open_webcams):
        webcam.release()


class Webcam:
    """A live camera feed as a pipeline input.

    Give it to the pipeline in place of an image: every filter receives the
    latest camera frame. The Qt and Dear PyGui windows refresh it ``fps``
    times per second (<kbd>Space</kbd> freezes / unfreezes the feed, the
    sliders keep working on the frozen frame); headless runs, snapshots and the
    other backends read one new frame per run.

    Args:
        device: camera index (``0``), device path or stream URL (OpenCV), an
            opened ``cv2.VideoCapture`` (or any object with
            ``read() -> (ok, frame_bgr)``), or a function returning a frame
            (RGB, any dtype; ``None`` when no new frame is ready).
        width, height: resolution asked to the camera (it may pick the closest it has).
        fps: refresh rate of the window (and frame rate asked to the camera).
        mirror: flip left / right, like a video call shows yourself.
        as_float: frames as float32 RGB in ``[0, 1]`` like ``Image.load_image``
            (default); ``False`` hands the uint8 frames over.
        warmup: frames dropped when the camera opens (the first ones are often dark).
        freeze_key: key freezing / unfreezing the feed in the window.

    Example:
        ```python
        @interactive_pipeline(gui="qt")
        def live(frame):
            edges = detect_edges(frame)
            return frame, edges

        live(Webcam(0))
        ```
    """

    def __init__(
        self,
        device: Union[int, str, Callable[[], Any], Any] = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: float = DEFAULT_LIVE_FPS,
        mirror: bool = False,
        as_float: bool = True,
        warmup: int = DEFAULT_WARMUP_FRAMES,
        freeze_key: str = " ",
    ) -> None:
        if isinstance(device, bool) or not (
            isinstance(device, (int, str)) or callable(device) or callable(getattr(device, "read", None))
        ):
            raise TypeError(
                "Webcam(device) takes a camera index, a device path / stream URL, an opened cv2.VideoCapture "
                f"or a function returning frames, got {type(device).__name__}"
            )
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        for name, value in (("width", width), ("height", height)):
            if value is not None and (not isinstance(value, int) or value <= 0):
                raise ValueError(f"{name} must be a positive int, got {value!r}")
        if warmup < 0:
            raise ValueError(f"warmup must be >= 0, got {warmup}")
        self.device = device
        self.width = width
        self.height = height
        self.fps = float(fps)
        self.mirror = mirror
        self.as_float = as_float
        self.warmup = warmup
        self.freeze_key = freeze_key
        self._capture: Any = None  # cv2.VideoCapture (or the user's reader)
        self._owns_capture = False
        self._lock = threading.Lock()  # one camera read at a time
        self._latest: Any = None
        self._latest_count = 0  # frames read so far
        self._latest_cond = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_request = 0.0
        self._warned_failure = False
        self._reader_error: Optional[BaseException] = None

    # ------------------------------------------------------------------ source
    @property
    def description(self) -> str:
        if isinstance(self.device, int):
            return f"camera {self.device}"
        if isinstance(self.device, str):
            return self.device
        return getattr(self.device, "__name__", type(self.device).__name__)

    @property
    def is_function(self) -> bool:
        return callable(self.device) and not callable(getattr(self.device, "read", None))

    def open(self) -> "Webcam":
        """Open the camera now (else it opens at the first frame). Raises ``RuntimeError`` when it cannot."""
        if self.is_function or self._capture is not None:
            return self
        if isinstance(self.device, (int, str)):
            try:
                import cv2
            except ImportError as exc:
                raise ImportError(
                    "Webcam needs OpenCV to read a camera: pip install opencv-python "
                    "(or give Webcam a function returning frames)"
                ) from exc
            capture = cv2.VideoCapture(self.device)
            if not capture.isOpened():
                capture.release()
                raise RuntimeError(
                    f"cannot open {self.description}: no camera there, or it is used by another program "
                    "(try another index: Webcam(1); on Linux `ls /dev/video*` lists the cameras)"
                )
            if self.width is not None:
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height is not None:
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            capture.set(cv2.CAP_PROP_FPS, self.fps)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # the latest frame, not a queue of old ones
            self._capture = capture
            self._owns_capture = True
        else:
            self._capture = self.device  # opened by the caller: released by the caller
        _open_webcams.add(self)
        for _ in range(self.warmup):
            self._read_raw()
        return self

    def _read_raw(self) -> Any:
        """One frame from the source, converted (None when it gave none)."""
        if self.is_function:
            grab: Callable[[], Any] = self.device  # type: ignore[assignment]  # is_function: a callable
            frame = grab()
            if frame is None:
                return None
            frame = np.asarray(frame)
        else:
            ok, frame = self._capture.read()
            if not ok or frame is None:
                return None
            if frame.ndim == 3 and frame.shape[-1] in (3, 4):
                frame = frame[..., 2::-1] if frame.shape[-1] == 3 else frame[..., [2, 1, 0, 3]]  # BGR -> RGB
        if self.mirror:
            frame = frame[:, ::-1]
        frame = np.ascontiguousarray(frame)
        if self.as_float and frame.dtype == np.uint8:
            frame = frame.astype(np.float32) / 255.0
        elif self.as_float and frame.dtype == np.uint16:
            frame = frame.astype(np.float32) / 65535.0
        return frame

    def _read_checked(self) -> Any:
        with self._lock:
            self.open()
            frame = self._read_raw()
        if frame is None and not self.is_function:
            raise RuntimeError(f"{self.description} gave no frame (disconnected, or used by another program?)")
        return frame

    # ------------------------------------------------------------------ frames
    def read(self) -> np.ndarray:
        """A new frame, read now (headless runs, snapshots)."""
        frame = self._read_checked()
        if frame is None:  # a function with nothing new: the previous frame
            frame = self._latest
            if frame is None:
                raise RuntimeError(f"{self.description} returned no frame")
        with self._latest_cond:
            self._latest = frame
            self._latest_count += 1
            self._latest_cond.notify_all()
        return frame

    def latest(self) -> np.ndarray:
        """The latest frame of the background reader (started when needed; windows)."""
        self._last_request = time.monotonic()
        if self._thread is None or not self._thread.is_alive():
            count = self._latest_count
            self._start_reader()
            with self._latest_cond:  # a fresh frame, not the one from before a freeze
                self._latest_cond.wait_for(
                    lambda: self._latest_count > count or not self._reader_alive(), timeout=FIRST_FRAME_TIMEOUT
                )
        if self._latest is None:
            if self._reader_error is not None:
                raise self._reader_error
            raise RuntimeError(f"{self.description} gave no frame within {FIRST_FRAME_TIMEOUT:g} s")
        return self._latest

    def _reader_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _start_reader(self) -> None:
        self._stop.clear()
        self._reader_error = None
        self._thread = threading.Thread(target=self._reader_loop, name=f"webcam {self.description}", daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        period = 1.0 / self.fps
        while not self._stop.is_set():
            if time.monotonic() - self._last_request > READER_IDLE_SECONDS:
                return  # nobody looks (frozen feed, window closed): the next latest() starts again
            tic = time.monotonic()
            try:
                frame = self._read_checked()
            except Exception as exc:  # reported by latest() in the GUI thread
                if self._latest is None:
                    self._reader_error = exc
                    return
                if not self._warned_failure:
                    logging.warning(f"{self.description}: {exc}; showing the last frame")
                    self._warned_failure = True
                frame = None
            if frame is not None:
                with self._latest_cond:
                    self._latest = frame
                    self._latest_count += 1
                    self._latest_cond.notify_all()
            if self.is_function or frame is None:
                # cameras pace themselves (read() waits for the next frame); functions do not
                self._stop.wait(max(period - (time.monotonic() - tic), 0.001))

    def release(self) -> None:
        """Stop reading and close the camera (it opens again at the next frame)."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        with self._lock:
            if self._capture is not None and self._owns_capture:
                self._capture.release()
            self._capture = None
            self._owns_capture = False
        _open_webcams.discard(self)

    def __enter__(self) -> "Webcam":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.release()

    def __deepcopy__(self, memo: dict) -> "Webcam":
        return self  # one camera: pipelines copying their inputs share it

    def __repr__(self) -> str:
        size = f", {self.width}x{self.height}" if self.width and self.height else ""
        return f"Webcam({self.description}{size}, {self.fps:g} fps)"


def is_webcam(value: Any) -> bool:
    return isinstance(value, Webcam)
