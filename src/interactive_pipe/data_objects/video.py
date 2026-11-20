"""``Video``: a sequence of frames given to a pipeline as one input.

The pipeline function is written for a single frame; the pipeline installs a
timeline (``TimelineControl``) and hands the current frame to the filters.
See ``interactive_pipe.headless.timeline`` and ``docs/guide/video.md``.

Sources, all read lazily (a frame is decoded when the timeline reaches it, and
the last ones are kept in a small cache):

- a video file (``.mp4``, ``.avi``, ``.mov``, ``.mkv``, ``.webm``... through
  OpenCV; ``.gif`` through Pillow when OpenCV is missing)
- a folder of images, a glob pattern (``"frames/*.png"``) or a list of image paths
- a numpy array ``(T, H, W)`` / ``(T, H, W, C)``, or a list of arrays
- a torch tensor ``(T, C, H, W)`` / ``(T, H, W, C)`` / ``(T, H, W)``, or a list of tensors
- an iterator / generator of frames, or an opened ``cv2.VideoCapture`` (a
  stream: read up to ``max_frames`` frames when the ``Video`` is created)
- any file format: a folder / glob pattern / list of paths with
  ``loader=`` (called with each path), or a ``FrameSource`` subclass (random
  access to the frames of anything: a container format, a camera SDK...)
- any lazy sequence (``len`` + ``[index]``, e.g. a torch ``Dataset``)

Per-frame metadata: a loader / ``FrameSource.read`` / sequence item may give
``(frame, {"iso": 100, ...})``, and ``FrameSource.metadata(index)`` may add
more. Filters read it as ``context["timeline"].metadata``.
"""

from __future__ import annotations

import glob as glob_module
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

#: file suffixes read as video files (everything else that exists is an image or a folder)
VIDEO_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".gif")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
DEFAULT_FPS = 25.0
#: frames read from a stream of unknown length (generator, webcam) when max_frames is not given
DEFAULT_STREAM_FRAMES = 500
#: decoded frames kept in memory by lazy sources (video files, image files, torch conversions)
DEFAULT_CACHE_FRAMES = 32
#: how the Qt / Dear PyGui windows show the timeline (``Video(..., timeline=...)``)
TIMELINE_DISPLAYS = ("shown", "collapsible", "collapsed", "hidden")


def _is_torch_tensor(value: Any) -> bool:
    value_type = type(value)
    return value_type.__module__.split(".")[0] == "torch" and value_type.__name__ in ("Tensor", "Parameter")


def _tensor_frame_to_numpy(tensor: Any) -> np.ndarray:
    """``(C, H, W)`` / ``(H, W, C)`` / ``(H, W)`` torch tensor -> ``(H, W[, C])`` numpy array."""
    array = tensor.detach().cpu().numpy()
    if array.ndim == 3 and array.shape[0] in (1, 3, 4) and array.shape[-1] not in (1, 3, 4):
        array = np.moveaxis(array, 0, -1)
    if array.ndim == 3 and array.shape[-1] == 1:
        array = array[..., 0]
    return array


def _split_metadata(item: Any) -> Tuple[Any, Dict[str, Any]]:
    """``(frame, {metadata})`` -> frame, metadata; a frame alone -> frame, {}."""
    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], Mapping):
        return item[0], dict(item[1])
    return item, {}


class FrameSource:
    """Random access to the frames of a custom ``Video`` source (and their metadata).

    Subclass it for a format ``Video`` cannot read: a container holding many
    frames, a camera SDK, frames computed on demand. Frames are read lazily
    (when the timeline reaches them) and cached by the ``Video``.

    Implement ``__len__`` and ``read(index)``; optionally ``metadata(index)``
    (a dict per frame, read by filters as ``context["timeline"].metadata``),
    ``fps`` and ``description``. ``read`` may also return
    ``(frame, metadata_dict)`` when both come from the same decoding.

    Example:
        ```python
        class RawBurst(FrameSource):
            fps = 30.0

            def __init__(self, path):
                self.file = BurstFile(path)  # your reader

            def __len__(self):
                return self.file.count

            def read(self, index):
                return self.file.frame(index)  # array (H, W[, C])

            def metadata(self, index):
                return {"exposure_ms": self.file.exposure(index)}

        pipe(Video(RawBurst("capture.burst")))
        ```
    """

    fps: Optional[float] = None
    description: str = ""

    def __len__(self) -> int:
        raise NotImplementedError

    def read(self, index: int) -> Any:
        """Frame ``index`` (``0 <= index < len(self)``), or ``(frame, metadata_dict)``."""
        raise NotImplementedError

    def metadata(self, index: int) -> Dict[str, Any]:
        """Metadata of frame ``index`` (merged under the one ``read`` returns)."""
        return {}


_FrameReader = FrameSource  # the built-in readers below


class _SequenceReader(_FrameReader):
    """Frames already in memory (array, tensor, list), converted by ``convert`` on access."""

    def __init__(self, frames: Any, convert: Optional[Callable[[Any], Any]] = None, description: str = "") -> None:
        self.frames = frames
        self.convert = convert
        self.description = description

    def __len__(self) -> int:
        return len(self.frames)

    def read(self, index: int) -> Any:
        frame = self.frames[index]
        return frame if self.convert is None else self.convert(frame)


class _ImageFilesReader(_FrameReader):
    """One file per frame: read by ``loader(path)`` when given, else as an image."""

    def __init__(self, paths: Sequence[Path], description: str, loader: Optional[Callable[[Path], Any]] = None) -> None:
        if not paths:
            raise ValueError(f"Video: no {'file' if loader else 'image'} found in {description}")
        self.paths = list(paths)
        self.description = description
        self.loader = loader

    def __len__(self) -> int:
        return len(self.paths)

    def read(self, index: int) -> Any:
        if self.loader is not None:
            return self.loader(self.paths[index])
        from interactive_pipe.data_objects.image import Image

        return Image.load_image(self.paths[index]).astype(np.float32)

    def metadata(self, index: int) -> Dict[str, Any]:
        return {"path": str(self.paths[index])}


class _OpenCVFileReader(_FrameReader):
    """Video file decoded by OpenCV: sequential reads are cheap, a jump seeks."""

    def __init__(self, path: Path) -> None:
        import cv2

        self.cv2 = cv2
        self.path = path
        self.capture = cv2.VideoCapture(str(path))
        if not self.capture.isOpened():
            raise ValueError(f"Video: OpenCV cannot open {path}")
        self.count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(self.capture.get(cv2.CAP_PROP_FPS) or 0.0)
        self.fps = fps if fps > 0 else None
        self.next_index = 0
        self.description = path.name
        if self.count <= 0:
            # some containers do not store their length: count by decoding once
            self.count = 0
            while self.capture.grab():
                self.count += 1
            self._seek(0)
        if self.count == 0:
            raise ValueError(f"Video: no frame could be read from {path}")

    def __len__(self) -> int:
        return self.count

    def _seek(self, index: int) -> None:
        self.capture.set(self.cv2.CAP_PROP_POS_FRAMES, index)
        self.next_index = index

    def read(self, index: int) -> np.ndarray:
        if index != self.next_index:
            self._seek(index)
        ok, frame = self.capture.read()
        if not ok:
            # the stored frame count can overestimate: show the last decodable frame
            if index > 0:
                self.count = index
                return self.read(index - 1)
            raise ValueError(f"Video: cannot decode frame {index} of {self.path}")
        self.next_index = index + 1
        if frame.ndim == 2:
            frame = self.cv2.cvtColor(frame, self.cv2.COLOR_GRAY2RGB)
        else:
            frame = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        return frame.astype(np.float32) / 255.0


class _PillowAnimationReader(_FrameReader):
    """Animated GIF / multi-page image read with Pillow (no OpenCV needed)."""

    def __init__(self, path: Path) -> None:
        from PIL import Image as PILImage

        self.image = PILImage.open(path)
        self.count = int(getattr(self.image, "n_frames", 1))
        duration_ms = self.image.info.get("duration")
        self.fps = 1000.0 / duration_ms if duration_ms else None
        self.description = path.name

    def __len__(self) -> int:
        return self.count

    def read(self, index: int) -> np.ndarray:
        self.image.seek(index)
        return np.asarray(self.image.convert("RGB"), dtype=np.float32) / 255.0


def _read_stream(stream: Any, max_frames: Optional[int], description: str) -> List[Any]:
    """Frames of an iterator / generator / opened ``cv2.VideoCapture``, up to ``max_frames``."""
    limit = DEFAULT_STREAM_FRAMES if max_frames is None else max_frames
    frames: List[Any] = []
    if hasattr(stream, "read") and hasattr(stream, "isOpened"):  # cv2.VideoCapture (file or camera)
        import cv2

        while len(frames) < limit:
            ok, frame = stream.read()
            if not ok:
                break
            code = cv2.COLOR_GRAY2RGB if frame.ndim == 2 else cv2.COLOR_BGR2RGB
            frames.append(cv2.cvtColor(frame, code).astype(np.float32) / 255.0)
        exhausted = len(frames) < limit
    else:
        iterator = iter(stream)
        exhausted = True
        for frame in iterator:
            frames.append(frame)
            if len(frames) >= limit:
                exhausted = False
                break
    if not frames:
        raise ValueError(f"Video: the {description} produced no frame")
    if not exhausted and max_frames is None:
        logging.warning(
            f"Video: kept the first {limit} frames of the {description} (a stream may be endless): "
            "pass max_frames=... to keep more or fewer"
        )
    return frames


def _paths_from_pattern(pattern: str) -> List[Path]:
    return [Path(found) for found in sorted(glob_module.glob(pattern))]


def _images_in_folder(folder: Path, every_file: bool = False) -> List[Path]:
    """Images of ``folder``, sorted; ``every_file``: all its files (a loader reads them), hidden ones aside."""
    return sorted(
        path
        for path in folder.iterdir()
        if (path.suffix.lower() in IMAGE_SUFFIXES) or (every_file and path.is_file() and not path.name.startswith("."))
    )


def _reader_for_path(path: Path, loader: Optional[Callable[[Path], Any]] = None) -> _FrameReader:
    if path.is_dir():
        return _ImageFilesReader(_images_in_folder(path, every_file=loader is not None), f"folder {path}", loader)
    if loader is not None:
        raise ValueError(
            f"Video({str(path)!r}, loader=...): a loader reads one frame per file, give a folder, a glob pattern "
            f"('{path.parent / ('*' + path.suffix)}') or a list of paths. For a file holding many frames, "
            "subclass interactive_pipe.FrameSource"
        )
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return _SequenceReader(np.load(path, mmap_mode="r"), np.asarray, path.name)
    if suffix not in VIDEO_SUFFIXES:
        if suffix in IMAGE_SUFFIXES:
            raise ValueError(
                f"Video({str(path)!r}) is a single image: pass a folder, a glob pattern "
                f"('{path.parent / ('*' + path.suffix)}') or a list of paths"
            )
        raise ValueError(f"Video: unsupported file type {path.suffix!r} ({path})")
    try:
        import cv2  # noqa: F401
    except ImportError:
        if suffix == ".gif":
            return _PillowAnimationReader(path)
        raise ImportError(
            f"Video({str(path)!r}) needs OpenCV to decode {suffix} files: pip install opencv-python-headless"
        ) from None
    return _OpenCVFileReader(path)


def _make_reader(
    source: Any, max_frames: Optional[int], to_numpy: bool, loader: Optional[Callable[[Path], Any]] = None
) -> _FrameReader:
    if loader is not None and not callable(loader):
        raise TypeError(f"Video: loader must be a function path -> frame, got {type(loader).__name__}")
    if loader is not None and not (
        isinstance(source, (str, Path))
        or (isinstance(source, (list, tuple)) and source and isinstance(source[0], (str, Path)))
    ):
        raise ValueError("Video: loader= reads files: give a folder, a glob pattern or a list of paths")
    if isinstance(source, Video):
        return source._reader
    if isinstance(source, FrameSource):
        if len(source) < 1:
            raise ValueError(f"Video: {type(source).__name__} has no frame")
        return source
    if isinstance(source, (str, Path)):
        text = str(source)
        if any(char in text for char in "*?["):
            return _ImageFilesReader(_paths_from_pattern(text), f"pattern {text!r}", loader)
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Video: {path} does not exist")
        return _reader_for_path(path, loader)
    if isinstance(source, np.ndarray):
        if source.ndim not in (3, 4):
            raise ValueError(
                f"Video: a numpy video is (T, H, W) or (T, H, W, C), got shape {source.shape}"
                + (": a single image is not a video, stack several (np.stack(frames))" if source.ndim == 2 else "")
            )
        return _SequenceReader(source, None, f"array {source.shape}")
    if _is_torch_tensor(source):
        tensor: Any = source
        if tensor.ndim not in (3, 4):
            raise ValueError(f"Video: a torch video is (T, C, H, W) or (T, H, W, C), got shape {tuple(tensor.shape)}")
        return _SequenceReader(tensor, _tensor_frame_to_numpy if to_numpy else None, f"tensor {tuple(tensor.shape)}")
    if isinstance(source, (list, tuple)):
        if not source:
            raise ValueError("Video: the list of frames is empty")
        first = source[0]
        if isinstance(first, (str, Path)):
            return _ImageFilesReader([Path(item) for item in source], f"{len(source)} files", loader)
        if _is_torch_tensor(first):
            return _SequenceReader(source, _tensor_frame_to_numpy if to_numpy else None, f"{len(source)} tensors")
        return _SequenceReader(source, None, f"{len(source)} frames")
    if hasattr(source, "__len__") and hasattr(source, "__getitem__") and not isinstance(source, (Mapping, bytes)):
        # a lazy sequence (torch Dataset, custom container): items read on access
        if len(source) < 1:
            raise ValueError(f"Video: {type(source).__name__} is empty")
        return _SequenceReader(source, None, f"{type(source).__name__} ({len(source)} items)")
    if hasattr(source, "__iter__") or (hasattr(source, "read") and hasattr(source, "isOpened")):
        description = "camera / video capture" if hasattr(source, "isOpened") else "frame iterator"
        frames = _read_stream(source, max_frames, description)
        convert = _tensor_frame_to_numpy if to_numpy and _is_torch_tensor(frames[0]) else None
        return _SequenceReader(frames, convert, f"{len(frames)} frames from a {description}")
    raise TypeError(
        f"Video: unsupported source {type(source).__name__}. Use a video file / folder / glob pattern path, "
        "a numpy array (T, H, W[, C]), a torch tensor, a list of frames or image paths, an iterator of frames, "
        "or a FrameSource"
    )


class Video:
    """A sequence of frames given to a pipeline in place of one image.

    Pass it as a pipeline input: the pipeline function stays written for a
    single frame, the window gets a timeline (play / pause, scrub, step) and
    the filters receive the current frame. Several ``Video`` inputs share the
    timeline (frames matched by time when their frame rates differ).

    Args:
        source: video file, image folder, glob pattern, list of image paths,
            numpy array ``(T, H, W[, C])``, torch tensor ``(T, C, H, W)`` /
            ``(T, H, W[, C])``, list of frames, iterator / generator of frames
            an opened ``cv2.VideoCapture``, a ``FrameSource`` or any lazy
            sequence (see the module docstring).
        fps: frame rate (playback speed, timecodes). Default: the file's, else 25.
        start, stop, step: keep ``frames[start:stop:step]`` only (like a slice).
        window: number of frames handed to the filters: 1 (default) gives the
            current frame; ``window=k`` gives the ``k`` frames ending at the
            current one, stacked on a new first axis (``(k, H, W[, C])``; the
            first frame is repeated at the start of the video). For temporal
            filters: frame differences, temporal denoising...
        max_frames: frames read from a stream (iterator, camera); default 500.
        to_numpy: torch frames are converted to numpy ``(H, W[, C])`` arrays
            (default); False hands the tensor slices themselves to the filters.
        cache_frames: decoded frames kept in memory by lazy sources.
        loader: reads a file of a folder / glob pattern / list of paths:
            ``loader(path) -> frame`` or ``-> (frame, metadata_dict)``. For
            any format (DNG, EXR, a custom raw format...).
        preview: ``preview(frame) -> image`` drawn on the timeline film strip,
            for frames that are not images to look at as they are (a raw
            mosaic, 10-bit data, a feature map). Default: the frame itself.
        timeline: how the Qt / Dear PyGui windows show the timeline:
            ``"shown"`` (default), ``"collapsible"`` (a button folds it to
            the transport row), ``"collapsed"`` (collapsible, starts
            folded) or ``"hidden"`` (no panel: space and the arrows still
            play and step). The first ``Video`` input decides.

    Example:
        ```python
        @interactive_pipeline(gui="qt")
        def grade(frame):
            graded = color_grade(frame)
            return frame, graded

        grade(Video("clip.mp4"))  # a timeline at the bottom of the window
        grade.headless(Video(frames_array), frame=10)  # frame 10 without a window
        ```
    """

    def __init__(
        self,
        source: Any,
        fps: Optional[float] = None,
        *,
        start: int = 0,
        stop: Optional[int] = None,
        step: int = 1,
        window: int = 1,
        max_frames: Optional[int] = None,
        to_numpy: bool = True,
        cache_frames: int = DEFAULT_CACHE_FRAMES,
        timeline: str = "shown",
        loader: Optional[Callable[[Path], Any]] = None,
        preview: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError(f"Video: window must be an int >= 1, got {window!r}")
        if isinstance(step, bool) or not isinstance(step, int) or step < 1:
            raise ValueError(f"Video: step must be an int >= 1, got {step!r}")
        if fps is not None and not fps > 0:
            raise ValueError(f"Video: fps must be positive, got {fps!r}")
        if max_frames is not None and max_frames < 1:
            raise ValueError(f"Video: max_frames must be >= 1, got {max_frames!r}")
        if timeline not in TIMELINE_DISPLAYS:
            raise ValueError(
                f"Video: timeline must be one of {', '.join(map(repr, TIMELINE_DISPLAYS))}, got {timeline!r}"
            )
        self.timeline_display = timeline
        self._reader = _make_reader(source, max_frames, to_numpy, loader)
        self._to_numpy = to_numpy
        if preview is not None and not callable(preview):
            raise TypeError(f"Video: preview must be a function frame -> image, got {type(preview).__name__}")
        self._preview = preview if preview is not None else (source._preview if isinstance(source, Video) else None)
        self._indexes = range(len(self._reader))[start:stop:step]
        if len(self._indexes) == 0:
            raise ValueError(f"Video: no frame left in {self._reader.description} with start={start}, stop={stop}")
        base_fps = fps if fps is not None else (source.fps if isinstance(source, Video) else self._reader.fps)
        if fps is None and step > 1 and base_fps is not None:
            base_fps = base_fps / step  # same duration
        self.fps = float(base_fps) if base_fps else DEFAULT_FPS
        self.window = window
        self._lock = threading.Lock()  # the GUI thread (thumbnails) and a worker run may read at once
        same_reader = isinstance(source, Video) and source._reader is self._reader
        self._cache: "OrderedDict[int, Any]" = source._cache if same_reader else OrderedDict()
        self._metadata: Dict[int, Dict[str, Any]] = source._metadata if same_reader else {}
        self._cache_frames = max(int(cache_frames), window + 1)
        self._thumbnails: dict = {}

    # ------------------------------------------------------------------ frames
    def __len__(self) -> int:
        return len(self._indexes)

    @property
    def duration(self) -> float:
        """Length in seconds."""
        return len(self) / self.fps

    @property
    def description(self) -> str:
        return self._reader.description or type(self._reader).__name__

    def frame(self, index: int) -> Any:
        """Frame ``index`` (clamped to the video), whatever ``window``."""
        index = min(max(int(index), 0), len(self) - 1)
        raw_index = self._indexes[index]
        with self._lock:
            cached = self._cache.get(raw_index)
            if cached is not None:
                self._cache.move_to_end(raw_index)
                return cached
            frame, metadata = _split_metadata(self._reader.read(raw_index))
            if self._to_numpy and _is_torch_tensor(frame):
                frame = _tensor_frame_to_numpy(frame)
            if len(self._metadata) > 100_000:
                self._metadata.clear()
            self._metadata[raw_index] = {**self._reader.metadata(raw_index), **metadata}
            if isinstance(frame, np.ndarray):
                frame.flags.writeable = False  # shared with the cache: filters get read-only frames anyway
            self._cache[raw_index] = frame
            while len(self._cache) > self._cache_frames:
                self._cache.popitem(last=False)
            return frame

    def metadata(self, index: int) -> Dict[str, Any]:
        """Metadata of frame ``index`` (clamped): what the source gave with it, ``{}`` if nothing.

        Files read from a folder / pattern / list also give ``"path"``.
        """
        index = min(max(int(index), 0), len(self) - 1)
        raw_index = self._indexes[index]
        known = self._metadata.get(raw_index)
        if known is None:
            self.frame(index)  # reading the frame gives its metadata
            known = self._metadata.get(raw_index, {})
        return dict(known)

    def __getitem__(self, index: int) -> Any:
        """What the filters receive at timeline position ``index``: a frame, or the
        ``window`` frames ending there, stacked on a new first axis."""
        if isinstance(index, slice):
            return [self[i] for i in range(len(self))[index]]
        if index < 0:
            index += len(self)
        if self.window == 1:
            return self.frame(index)
        frames = [self.frame(max(index - offset, 0)) for offset in range(self.window - 1, -1, -1)]
        if _is_torch_tensor(frames[0]):
            import torch

            return torch.stack(frames)
        return np.stack(frames)

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def with_window(self, window: int) -> "Video":
        """The same video (same decoded frames) handing ``window`` frames to the filters."""
        clone = Video.__new__(Video)
        clone.__dict__.update(self.__dict__)
        clone._thumbnails = self._thumbnails
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError(f"Video: window must be an int >= 1, got {window!r}")
        clone.window = window
        clone._cache_frames = max(self._cache_frames, window + 1)
        return clone

    def index_at(self, seconds: float) -> int:
        """Frame shown at ``seconds`` (clamped to the video)."""
        return min(max(int(round(seconds * self.fps)), 0), len(self) - 1)

    # ------------------------------------------------------------------ timeline thumbnails
    def thumbnail(self, index: int, height: int = 48) -> np.ndarray:
        """``(h, w, 3)`` uint8 preview of frame ``index`` (timeline film strip)."""
        index = min(max(int(index), 0), len(self) - 1)
        key = (index, height)
        cached = self._thumbnails.get(key)
        if cached is not None:
            return cached
        from PIL import Image as PILImage

        from interactive_pipe.graphical.display import prepare_display

        frame = self.frame(index)
        if self._preview is not None:
            frame = self._preview(frame)
        if _is_torch_tensor(frame):
            frame = _tensor_frame_to_numpy(frame)
        rgb = prepare_display(np.asarray(frame))
        rgb8 = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        width = max(1, round(rgb8.shape[1] * height / max(rgb8.shape[0], 1)))
        bilinear = getattr(getattr(PILImage, "Resampling", PILImage), "BILINEAR")  # Pillow < 9.1: no Resampling
        small = np.asarray(PILImage.fromarray(rgb8).resize((width, height), bilinear))
        if len(self._thumbnails) > 256:
            self._thumbnails.clear()
        self._thumbnails[key] = small
        return small

    # ------------------------------------------------------------------ pipeline buffers
    def __deepcopy__(self, memo: dict) -> "Video":
        # a read-only source: pipeline input buffers are deep-copied before runs, never this one
        return self

    def __repr__(self) -> str:
        window = f", window={self.window}" if self.window > 1 else ""
        return f"Video({self.description}, {len(self)} frames, {self.fps:g} fps{window})"


def is_video(value: Any) -> bool:
    return isinstance(value, Video)


VideoSource = Union[str, Path, np.ndarray, Sequence[Any], FrameSource, Video]
