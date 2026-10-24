"""Render a `TimeControl`-driven pipeline to an animated GIF or a PNG frame sequence.

Pure headless: no GUI import. The GUI "Export animation" action calls
`export_animation` with its defaults (5 s at 10 fps); call it directly to
change the duration, frame rate, output cell or time control.
"""

from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import numpy as np

from interactive_pipe.headless.control import TimeControl
from interactive_pipe.headless.pipeline import HeadlessPipeline

PNG_SUFFIX = ".png"
GIF_SUFFIX = ".gif"


def find_time_control(
    pipeline: HeadlessPipeline, time_control: Optional[Union[str, TimeControl]] = None
) -> TimeControl:
    """Return the TimeControl of `pipeline` (by name or instance when several exist)."""
    controls = [ctrl for ctrl in getattr(pipeline, "controls", None) or [] if isinstance(ctrl, TimeControl)]
    if isinstance(time_control, TimeControl):
        if not any(ctrl is time_control for ctrl in controls):
            raise ValueError(f"TimeControl {time_control.name!r} is not a control of this pipeline")
        return time_control
    if time_control is not None:
        if not isinstance(time_control, str):
            raise TypeError(f"time_control must be a name, a TimeControl or None, got {type(time_control)}")
        matches = [ctrl for ctrl in controls if ctrl.name == time_control]
        if not matches:
            names = [ctrl.name for ctrl in controls]
            raise ValueError(f"No TimeControl named {time_control!r} in this pipeline (available: {names})")
        return matches[0]
    if not controls:
        raise ValueError("No TimeControl in this pipeline")
    if len(controls) > 1:
        names = [ctrl.name for ctrl in controls]
        raise ValueError(f"Several TimeControls in this pipeline {names}: pick one with time_control=<name>")
    return controls[0]


def _select_output(result: Any, output: Union[int, Tuple[int, int], None]) -> Any:
    """Pick one output cell from a run result (tuple, 2D list or single value)."""
    if result is None:
        raise ValueError("The pipeline produced no output")
    is_grid = isinstance(result, list) and any(isinstance(row, (list, tuple)) for row in result)
    if output is None:
        cells: List[Any] = []
        if is_grid:
            for row in result:
                cells.extend(row if isinstance(row, (list, tuple)) else [row])
        elif isinstance(result, (list, tuple)):
            cells = list(result)
        else:
            cells = [result]
        for cell in cells:
            if cell is not None:
                return cell
        raise ValueError("The pipeline produced no output")
    if isinstance(output, tuple):
        if len(output) != 2:
            raise ValueError(f"output must be an index or a (row, col) pair, got {output}")
        row, col = output
        if not is_grid:
            if row != 0:
                raise IndexError(f"output {output}: the pipeline outputs are not a 2D layout")
            cell = result[col] if isinstance(result, (list, tuple)) else result
        else:
            cell = result[row][col]
    elif isinstance(output, int):
        if is_grid:
            raise ValueError(f"output={output}: the outputs form a 2D layout, use output=(row, col)")
        cell = result[output] if isinstance(result, (list, tuple)) else result
    else:
        raise TypeError(f"output must be an int, a (row, col) tuple or None, got {type(output)}")
    if cell is None:
        raise ValueError(f"Output {output} is empty")
    return cell


def _to_rgb_uint8(frame: Any) -> np.ndarray:
    """Convert an output image (float in [0, 1] or uint8, HxW or HxWxC) to HxWx3 uint8."""
    if not isinstance(frame, np.ndarray):
        raise TypeError(
            f"Animation export needs image outputs (numpy arrays), got {type(frame).__name__}: "
            "pick an image output with output=<index> or output=(row, col)"
        )
    if frame.ndim == 3 and frame.shape[-1] == 1:
        frame = frame[..., 0]
    if frame.ndim == 2:
        frame = np.stack([frame] * 3, axis=-1)
    if frame.ndim != 3 or frame.shape[-1] not in (3, 4):
        raise TypeError(f"Animation export needs HxW or HxWx3 images, got shape {frame.shape}")
    frame = frame[..., :3]
    if frame.dtype == np.uint8:
        return np.ascontiguousarray(frame)
    return (np.clip(frame.astype(np.float64), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def export_animation(
    pipeline: HeadlessPipeline,
    path: Union[str, Path],
    *,
    duration: float = 5.0,
    fps: float = 10.0,
    time_control: Optional[Union[str, TimeControl]] = None,
    output: Union[int, Tuple[int, int], None] = None,
    loop: int = 0,
) -> Path:
    """Render `duration` seconds of a TimeControl-driven pipeline to disk.

    Frame `k` is rendered with the time control set to `k / fps` seconds.

    Args:
        pipeline: pipeline holding a `TimeControl` (e.g. `gui.pipeline`).
        path: `.gif` file -> animated GIF (Pillow); a directory, a `.png` path or a
            path without suffix -> numbered PNG frames `<stem>_0000.png`, ...
            (written inside the directory, or next to the path).
        duration: animation length in seconds.
        fps: frames per second.
        time_control: name (or instance) of the TimeControl to drive; required
            only when the pipeline has several.
        output: which output to record: an index into the output tuple, a
            `(row, col)` cell of a 2D layout, or None for the first non-empty one.
        loop: GIF loop count (0 = forever).

    Returns:
        The written GIF path, or the directory holding the PNG frames.

    The control's previous value is restored (and the pipeline re-run) afterwards.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    if loop < 0:
        raise ValueError(f"loop must be >= 0, got {loop}")
    n_frames = int(duration * fps)
    if n_frames < 1:
        raise ValueError(f"duration * fps must give at least one frame (duration={duration}, fps={fps})")
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in ("", GIF_SUFFIX, PNG_SUFFIX) and not path.is_dir():
        raise ValueError(f"Unsupported animation format {path.suffix!r}: use .gif, .png or a directory")
    ctrl = find_time_control(pipeline, time_control)

    from PIL import Image as PILImage

    previous_value = ctrl.value
    frames: List[np.ndarray] = []
    try:
        for k in range(n_frames):
            ctrl.value = k / fps
            frames.append(_to_rgb_uint8(_select_output(pipeline.run(), output)))
    except BaseException:
        ctrl.value = previous_value
        raise
    # Back to the state shown before the export (results, filter parameters)
    ctrl.value = previous_value
    pipeline.run()

    if suffix == GIF_SUFFIX and not path.is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
        images = [PILImage.fromarray(frame) for frame in frames]
        images[0].save(
            path,
            save_all=True,
            append_images=images[1:],
            duration=1000.0 / fps,
            loop=loop,
        )
        return path
    if path.is_dir() or suffix == "":
        folder, stem = path, path.name or "frame"
    else:
        folder, stem = path.parent, path.stem
    folder.mkdir(parents=True, exist_ok=True)
    for k, frame in enumerate(frames):
        PILImage.fromarray(frame).save(folder / f"{stem}_{k:04d}{PNG_SUFFIX}")
    return folder
