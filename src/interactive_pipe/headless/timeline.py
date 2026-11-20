"""Video inputs: the timeline control and the frame filters a pipeline installs for them.

A pipeline input given as a ``Video`` is not handed to the filters: the
pipeline puts a small *frame filter* in front of them (``video_<input>``,
reading the ``Video`` buffer and writing the current frame in its place) and a
``TimelineControl`` drives the frame index of every frame filter. Everything
else is the ordinary machinery: the cache recomputes what follows the frame
filter when the frame changes, ``snapshot`` / ``sweep`` / ``describe`` /
tuning files see a control named ``frame``, the GUIs show a timeline (an int
slider on the backends without a dedicated widget).

Filters may read the timeline position with ``context["timeline"]`` (a
``Timeline``: ``frame``, ``time``, ``fps``, ``n_frames``, and the
``metadata`` of the frame shown).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.data_objects.video import Video
from interactive_pipe.headless.control import Control

if TYPE_CHECKING:
    from interactive_pipe.headless.pipeline import HeadlessPipeline

#: control name of the timeline ("timeline" when a filter parameter already uses it)
TIMELINE_NAME = "frame"
FALLBACK_TIMELINE_NAME = "timeline"
#: context key holding the ``Timeline`` position, written by the frame filters
CONTEXT_KEY = "timeline"
FRAME_FILTER_PREFIX = "video_"


def timecode(seconds: float, fps: Optional[float] = None) -> str:
    """``"01:02.40"`` (``"1:01:02.40"`` past one hour)."""
    seconds = max(seconds, 0.0)
    hours, rest = divmod(seconds, 3600.0)
    minutes, secs = divmod(rest, 60.0)
    text = f"{int(minutes):02d}:{secs:05.2f}"
    return f"{int(hours)}:{text}" if hours >= 1 else text


@dataclass(frozen=True)
class Timeline:
    """Position of the timeline, readable by filters as ``context["timeline"]``.

    ``metadata``: the metadata of the frame shown (first ``Video`` input), as
    its source gives it (``loader`` / ``FrameSource``; ``"path"`` for files),
    ``{}`` when there is none. ``inputs_metadata``: the same for every
    ``Video`` input, by input name.
    """

    frame: int
    n_frames: int
    fps: float
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)
    inputs_metadata: Dict[Any, Dict[str, Any]] = field(default_factory=dict, compare=False)

    @property
    def time(self) -> float:
        """Seconds since the first frame."""
        return self.frame / self.fps

    @property
    def duration(self) -> float:
        return self.n_frames / self.fps

    @property
    def progress(self) -> float:
        """Position in [0, 1]."""
        return self.frame / max(self.n_frames - 1, 1)

    def __str__(self) -> str:
        return f"{timecode(self.time)} / {timecode(self.duration)} · frame {self.frame}/{self.n_frames - 1}"


class TimelineControl(Control):
    """Frame index of the ``Video`` inputs of a pipeline (an int in ``[0, n_frames - 1]``).

    Created by the pipeline when an input is a ``Video``: you do not declare
    it. The Qt and Dear PyGui windows show it as a timeline (film strip,
    play / pause, step, timecode; space plays / pauses, the left / right
    arrows step one frame); the other backends as an int slider. Its name is
    ``frame``: ``pipe.snapshot(path, Video(...), frame=10)``,
    ``pipe.sweep(path, Video(...), frame=[0, 50, 100])``.

    Attributes:
        fps: frame rate of the timeline (the first video's).
        display: ``"shown"``, ``"collapsible"``, ``"collapsed"`` or ``"hidden"``
            (``Video(..., timeline=...)`` of the first video).
        collapsed: the panel is folded to its transport row (collapsible displays).
        loop: playback starts over at the end (else it stops there).
        playing: playback state, shared by the widgets.
        videos: the ``Video`` inputs it drives (film strip thumbnails).
    """

    def __init__(
        self,
        n_frames: int,
        fps: float = 25.0,
        name: str = TIMELINE_NAME,
        loop: bool = True,
        autoplay: bool = False,
        tooltip: Optional[str] = None,
        display: str = "shown",
    ) -> None:
        if n_frames < 1:
            raise ValueError(f"a timeline needs at least one frame, got {n_frames}")
        super().__init__(
            value_default=0,
            value_range=[0, n_frames - 1],
            name=name,
            step=1,
            tooltip=tooltip if tooltip is not None else "video frame: space plays / pauses, ← → step",
        )
        self.fps = float(fps)
        self.loop = loop
        self.autoplay = autoplay
        self.playing = autoplay
        self.videos: List[Video] = []
        self.display = "shown"
        self.collapsed = False
        self.set_display(display)

    @property
    def collapsible(self) -> bool:
        return self.display in ("collapsible", "collapsed")

    def set_display(self, display: str) -> None:
        """``"shown"``, ``"collapsible"``, ``"collapsed"`` (collapsible, folded) or ``"hidden"``."""
        from interactive_pipe.data_objects.video import TIMELINE_DISPLAYS

        if display not in TIMELINE_DISPLAYS:
            raise ValueError(
                f"timeline display must be one of {', '.join(map(repr, TIMELINE_DISPLAYS))}, got {display!r}"
            )
        if display != self.display:
            self.collapsed = display == "collapsed"
        self.display = display

    @property
    def n_frames(self) -> int:
        return int(self.value_range[1]) + 1  # type: ignore[index]

    @property
    def position(self) -> Timeline:
        return Timeline(frame=int(self.value), n_frames=self.n_frames, fps=self.fps)

    def set_length(self, n_frames: int, fps: float) -> None:
        """Resize the timeline (new videos given to the pipeline); the frame is kept when it still exists."""
        self.value_range = [0, max(int(n_frames), 1) - 1]
        self.fps = float(fps)
        if self._value > self.value_range[1]:
            self._value = self.value_range[1]

    def next_frame(self, step: int = 1) -> Optional[int]:
        """Frame ``step`` frames away (wrapping when ``loop``); None at the end without loop."""
        target = int(self.value) + step
        last = self.n_frames - 1
        if 0 <= target <= last:
            return target
        if not self.loop:
            return None
        return target % self.n_frames

    def label(self, frame: Optional[int] = None) -> str:
        """``"00:01.20 / 00:12.00 · frame 30/299"``"""
        index = int(self.value if frame is None else frame)
        return str(Timeline(frame=index, n_frames=self.n_frames, fps=self.fps))

    def __repr__(self) -> str:
        return f"TimelineControl({self.name!r}, {self.n_frames} frames at {self.fps:g} fps)"


#: parameter of the frame filters driven by the timeline (not ``frame``: a keyword
#: ``frame=`` names the timeline control, never a parameter of every filter having one)
FRAME_PARAMETER = "frame_index"


class VideoFrameFilter(FilterCore):
    """Reads frame ``frame_index`` of the ``Video`` buffer ``input_name`` and replaces the buffer with it."""

    def __init__(self, input_name: Any, name: str) -> None:
        self.input_name = input_name
        self.timeline_fps = 25.0
        self.timeline_frames = 1
        self.first_input: Any = input_name  # whose metadata is Timeline.metadata
        super().__init__(name=name, inputs=[input_name], outputs=[input_name])

    def apply(self, video: Any, frame_index: int = 0) -> Any:  # type: ignore[override]
        if not isinstance(video, Video):
            raise TypeError(f"input '{self.input_name}' is not a Video anymore (got {type(video).__name__})")
        frame = int(frame_index)
        # several videos share the timeline: frames are matched by time
        if abs(video.fps - self.timeline_fps) > 1e-6:
            index = video.index_at(frame / self.timeline_fps)
        else:
            index = min(frame, len(video) - 1)
        frames = video[index]
        from interactive_pipe.core.context import _user_context

        user_context = _user_context.get()
        if user_context is not None:
            previous = user_context.get(CONTEXT_KEY)
            # the frame filters of the other inputs ran (or run) at the same position
            inputs_metadata = dict(previous.inputs_metadata) if isinstance(previous, Timeline) else {}
            inputs_metadata[self.input_name] = video.metadata(index)
            user_context[CONTEXT_KEY] = Timeline(
                frame=frame,
                n_frames=self.timeline_frames,
                fps=self.timeline_fps,
                metadata=inputs_metadata.get(self.first_input, {}),
                inputs_metadata=inputs_metadata,
            )
        return frames


def timeline_of(pipeline: Any) -> Optional[TimelineControl]:
    """The pipeline's timeline (None when no input is a ``Video``)."""
    for ctrl in getattr(pipeline, "controls", None) or []:
        if isinstance(ctrl, TimelineControl):
            return ctrl
    return None


def videos_in(inputs_routing: Sequence[Any], values: Any) -> Dict[Any, Video]:
    """``{input name: Video}`` among pipeline inputs given positionally (list) or by name (dict)."""
    if values is None:
        return {}
    if isinstance(values, dict):
        return {name: value for name, value in values.items() if isinstance(value, Video)}
    if not isinstance(values, (list, tuple)):
        values = [values]
    return {name: value for name, value in zip(inputs_routing or [], values) if isinstance(value, Video)}


def _free_name(wanted: str, taken: set) -> str:
    name, suffix = wanted, 1
    while name in taken:
        name = f"{wanted}_{suffix}"
        suffix += 1
    return name


def install_videos(pipeline: "HeadlessPipeline", videos: Dict[Any, Video]) -> Optional[TimelineControl]:
    """Put a frame filter in front of the pipeline for every ``Video`` input, all driven by one timeline.

    Idempotent; called whenever inputs are given. Inputs that are no longer a
    ``Video`` lose their frame filter. Returns the timeline (None without video).
    """
    if getattr(pipeline, "controls", None) is None:
        pipeline.controls = []
    frame_filters = {filt.input_name: filt for filt in pipeline.filters if isinstance(filt, VideoFrameFilter)}
    timeline = timeline_of(pipeline)
    if not videos and not frame_filters:
        return None
    changed = False
    for input_name, filt in list(frame_filters.items()):
        if input_name not in videos:
            pipeline.filters.remove(filt)
            del frame_filters[input_name]
            changed = True
    if not videos:
        if timeline is not None:
            pipeline.controls.remove(timeline)
        user_context = getattr(pipeline, "_user_context", None)
        if user_context is not None:
            user_context.pop(CONTEXT_KEY, None)  # no stale position for the filters
        pipeline.reset_cache()
        return None
    routing = list(pipeline.inputs_routing or [])
    ordered = sorted(videos, key=lambda name: routing.index(name) if name in routing else len(routing))
    master = videos[ordered[0]]
    # timeline long enough for every video at the master frame rate
    n_frames = max(len(master), *(int(round(len(video) / video.fps * master.fps)) for video in videos.values()))
    if timeline is None:
        taken_parameters = {name for filt in pipeline.filters for name in (getattr(filt, "values", None) or {})}
        taken_controls = {ctrl.name for ctrl in pipeline.controls}
        name = TIMELINE_NAME if TIMELINE_NAME not in taken_parameters | taken_controls else FALLBACK_TIMELINE_NAME
        timeline = TimelineControl(
            n_frames, fps=master.fps, name=_free_name(name, taken_controls), display=master.timeline_display
        )
        pipeline.controls.insert(0, timeline)
        changed = True
    else:
        timeline.set_length(n_frames, master.fps)
        timeline.set_display(master.timeline_display)
    taken_filters = {filt.name for filt in pipeline.filters}
    new_filters = []
    for input_name in ordered:
        filt = frame_filters.get(input_name)
        if filt is None:
            filt = VideoFrameFilter(input_name, _free_name(f"{FRAME_FILTER_PREFIX}{input_name}", taken_filters))
            taken_filters.add(filt.name)
            filt.global_params = pipeline.global_params
            filt.framework_state = pipeline.framework_state
            new_filters.append(filt)
            changed = True
        filt.timeline_fps = timeline.fps
        filt.timeline_frames = timeline.n_frames
        filt.first_input = ordered[0]
    if new_filters:
        pipeline.filters[0:0] = new_filters
    # one widget drives every frame filter (targets rebuilt in input order)
    frame_filter_list = [filt for filt in pipeline.filters if isinstance(filt, VideoFrameFilter)]
    timeline.filter_to_connect = None
    for filt in frame_filter_list:
        timeline._add_target(filt, FRAME_PARAMETER)
        filt.values = {FRAME_PARAMETER: timeline.value}
    timeline.videos = [videos[name] for name in ordered]
    if changed:
        logging.debug(f"timeline {timeline!r} drives {[filt.name for filt in frame_filter_list]}")
        pipeline.reset_cache()
    return timeline
