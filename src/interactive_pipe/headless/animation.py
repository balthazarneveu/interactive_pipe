"""Render a `TimeControl`-driven pipeline to an animated GIF or a PNG frame sequence.

Pure headless: no GUI import. The GUI "Export animation" action calls
`export_animation` with its defaults (5 s at 10 fps); call it directly to
change the duration, frame rate, output cell or time control.
"""

from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import numpy as np

from interactive_pipe.graphical.display import prepare_display
from interactive_pipe.headless.control import TimeControl
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.headless.timeline import TimelineControl, timeline_of

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


def _prepared_result(pipeline: HeadlessPipeline, result: Any) -> Any:
    """`result` with every output converted for display like the GUI shows it
    (``layout.style`` heatmap options, matplotlib figures rasterised), same structure."""
    framework_state = getattr(pipeline, "framework_state", None)
    styles = framework_state.output_styles if framework_state is not None else {}
    names = getattr(pipeline, "outputs", None)
    producers = {out: filt.name for filt in getattr(pipeline, "filters", []) for out in (filt.outputs or [])}

    def name_at(*index: int) -> Any:
        try:
            value = names
            for position in index:
                value = value[position]  # type: ignore[index]
            return value
        except (IndexError, KeyError, TypeError):
            return None

    def prepare(content: Any, *index: int) -> Any:
        if content is None:
            return None
        name = name_at(*index)
        style = styles.get(name) if isinstance(name, (str, int)) else None
        # name the output and its filter in a DisplayError, like the GUIs and snapshots do
        return prepare_display(
            content, style, name=None if name is None else str(name), filter_name=producers.get(name)
        )

    is_grid = isinstance(result, list) and any(isinstance(row, (list, tuple)) for row in result)
    if is_grid:
        return [
            [prepare(cell, r, c) for c, cell in enumerate(row)] if isinstance(row, (list, tuple)) else prepare(row, r)
            for r, row in enumerate(result)
        ]
    if isinstance(result, (list, tuple)):
        return type(result)(prepare(cell, i) for i, cell in enumerate(result))
    return prepare(result, 0)


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


def _animated_control(
    pipeline: HeadlessPipeline, time_control: Optional[Union[str, TimeControl, TimelineControl]]
) -> Union[TimeControl, TimelineControl]:
    """The control an animation export drives: the named one, else the TimeControl,
    else the timeline of a ``Video`` input."""
    timeline = timeline_of(pipeline)
    if timeline is not None and (time_control is timeline or time_control == timeline.name):
        return timeline
    if time_control is None and timeline is not None:
        has_time = any(isinstance(ctrl, TimeControl) for ctrl in getattr(pipeline, "controls", None) or [])
        if not has_time:
            return timeline
    return find_time_control(pipeline, time_control)  # type: ignore[arg-type]


def export_animation(
    pipeline: HeadlessPipeline,
    path: Union[str, Path],
    *,
    duration: Optional[float] = None,
    fps: Optional[float] = None,
    time_control: Optional[Union[str, TimeControl, TimelineControl]] = None,
    output: Union[int, Tuple[int, int], None] = None,
    loop: int = 0,
) -> Path:
    """Render `duration` seconds of a TimeControl-driven pipeline to disk.

    Frame `k` is rendered with the time control set to `k / fps` seconds.
    A pipeline whose input is a ``Video`` (and without TimeControl) renders its
    timeline instead: every frame by default, at the video frame rate.

    Args:
        pipeline: pipeline holding a `TimeControl` (e.g. `gui.pipeline`).
        path: `.gif` file -> animated GIF (Pillow); a directory, a `.png` path or a
            path without suffix -> numbered PNG frames `<stem>_0000.png`, ...
            (written inside the directory, or next to the path).
        duration: animation length in seconds (default 5 s; a video: all of it).
        fps: frames per second (default 10; a video: its frame rate).
        time_control: name (or instance) of the TimeControl to drive; required
            only when the pipeline has several. The timeline of a ``Video``
            input is named ``frame``.
        output: which output to record: an index into the output tuple, a
            `(row, col)` cell of a 2D layout, or None for the first non-empty one.
        loop: GIF loop count (0 = forever).

    Returns:
        The written GIF path, or the directory holding the PNG frames.

    The control's previous value is restored (and the pipeline re-run) afterwards.
    """
    ctrl = _animated_control(pipeline, time_control)
    is_timeline = isinstance(ctrl, TimelineControl)
    if fps is None:
        fps = ctrl.fps if isinstance(ctrl, TimelineControl) else 10.0
    if duration is None:
        duration = ctrl.n_frames / ctrl.fps if isinstance(ctrl, TimelineControl) else 5.0
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    if loop < 0:
        raise ValueError(f"loop must be >= 0, got {loop}")
    n_frames = int(round(duration * fps, 6))
    if n_frames < 1:
        raise ValueError(f"duration * fps must give at least one frame (duration={duration}, fps={fps})")
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in ("", GIF_SUFFIX, PNG_SUFFIX) and not path.is_dir():
        raise ValueError(f"Unsupported animation format {path.suffix!r}: use .gif, .png or a directory")

    from PIL import Image as PILImage

    previous_value = ctrl.value
    # every frame of the video in turn: read ahead (exporting fewer frames, it would decode skipped ones)
    read_ahead = is_timeline and abs(fps - ctrl.fps) < 1e-6
    frames: List[np.ndarray] = []
    try:
        for k in range(n_frames):
            seconds = k / fps
            ctrl.value = min(int(round(seconds * ctrl.fps)), ctrl.n_frames - 1) if is_timeline else seconds
            if read_ahead and isinstance(ctrl, TimelineControl):
                ctrl.preload()  # the next frames decode while this one is processed
            result = _prepared_result(pipeline, pipeline.run())
            frames.append(_to_rgb_uint8(_select_output(result, output)))
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
