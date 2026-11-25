"""Video and audio inputs: the timeline control and the filters a pipeline installs for them.

A pipeline input given as a ``Video`` is not handed to the filters: the
pipeline puts a small *frame filter* in front of them (``video_<input>``,
reading the ``Video`` buffer and writing the current frame in its place) and a
``TimelineControl`` drives the frame index of every frame filter. Everything
else is the ordinary machinery: the cache recomputes what follows the frame
filter when the frame changes, ``snapshot`` / ``sweep`` / ``describe`` /
tuning files see a control named ``frame``, the GUIs show a timeline (an int
slider on the backends without a dedicated widget).

An input given as an ``AudioClip`` gets an *audio filter* (``audio_<input>``)
writing the whole signal in place of the clip: it does not depend on the
playhead, so moving it never recomputes the audio filters. The clip shares
the timeline (one waveform lane, next to the video lanes); without any
``Video`` a *clock filter* (``timeline``, ``cache_transparent``) writes the
position in the context.

Filters may read the timeline position with ``context["timeline"]`` (a
``Timeline``: ``frame``, ``time``, ``fps``, ``n_frames``, and the
``metadata`` of the frame shown).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.data_objects.audio_clip import AudioClip
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
AUDIO_FILTER_PREFIX = "audio_"
CLOCK_FILTER_NAME = "timeline"
#: ticks per second of a timeline without video (playhead resolution of a sound)
AUDIO_TIMELINE_FPS = 30.0


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
    input on the timeline, by input name; an ``AudioClip`` input gives
    ``sample_rate``, ``duration``, ``channels`` (and ``path``).
    """

    frame: int
    n_frames: int
    fps: float
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)
    inputs_metadata: Dict[Any, Dict[str, Any]] = field(default_factory=dict, compare=False)
    has_video: bool = field(default=True, compare=False)  # False: sounds only, no frame number shown

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
        text = f"{timecode(self.time)} / {timecode(self.duration)}"
        return f"{text} · frame {self.frame}/{self.n_frames - 1}" if self.has_video else text


def frame_of_video(video: Video, frame: int, timeline_fps: float) -> int:
    """Frame of ``video`` shown at timeline frame ``frame`` (videos sharing a timeline are matched by time)."""
    if abs(video.fps - timeline_fps) > 1e-6:
        return video.index_at(frame / timeline_fps)
    return min(max(int(frame), 0), len(video) - 1)


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
        videos: the ``Video`` inputs it drives, in input order.
        audio_clips: the ``AudioClip`` inputs on the timeline, in input order.
        track_names: the input name of each lane of the film strip.
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
        self.audio_clips: List[AudioClip] = []
        self.track_names: List[Any] = []
        self._tracks: Optional[List[Tuple[Any, Any]]] = None
        self.display = "shown"
        self.collapsed = False
        self.set_display(display)

    @property
    def tracks(self) -> List[Tuple[Any, Any]]:
        """``(input name, Video or AudioClip)`` of every input on the timeline, in input order: one lane each."""
        if self._tracks is not None:
            return list(self._tracks)
        names = self.track_names if len(self.track_names) == len(self.videos) else range(len(self.videos))
        return list(zip(names, self.videos))

    @property
    def has_video(self) -> bool:
        """False when the timeline holds sounds only (no frame number shown)."""
        return bool(self.videos) or not self.audio_clips

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
        return Timeline(frame=int(self.value), n_frames=self.n_frames, fps=self.fps, has_video=self.has_video)

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

    def preload(self, frame: Optional[int] = None) -> None:
        """Decode the frames after ``frame`` (default: the current one) of every video, in the background.

        Called by the GUI timelines whenever the playhead moves; each video
        reads ``Video(..., preload=...)`` frames ahead.
        """
        index = int(self.value if frame is None else frame)
        for video in self.videos:
            video.preload_from(frame_of_video(video, index, self.fps))

    def buffered(self) -> List[int]:
        """Timeline frames whose first video frame is decoded and in memory (sorted)."""
        if not self.videos:
            return []
        return self.videos[0].buffered()

    @property
    def background_version(self) -> tuple:
        """Changes when a video decoded a frame or built a thumbnail (redraw the film strip)."""
        return tuple(video.background_version for video in self.videos)

    def label(self, frame: Optional[int] = None) -> str:
        """``"00:01.20 / 00:12.00 · frame 30/299"``"""
        index = int(self.value if frame is None else frame)
        return str(Timeline(frame=index, n_frames=self.n_frames, fps=self.fps, has_video=self.has_video))

    def __repr__(self) -> str:
        return f"TimelineControl({self.name!r}, {self.n_frames} frames at {self.fps:g} fps)"


#: parameter of the frame filters driven by the timeline (not ``frame``: a keyword
#: ``frame=`` names the timeline control, never a parameter of every filter having one)
FRAME_PARAMETER = "frame_index"


class _PositionWriter:
    """Writes ``context["timeline"]`` (shared by the frame filters and the clock filter)."""

    timeline_fps: float
    timeline_frames: int
    has_video: bool
    first_input: Any
    static_metadata: Dict[Any, Dict[str, Any]]

    def _init_position(self, first_input: Any) -> None:
        self.timeline_fps = 25.0
        self.timeline_frames = 1
        self.has_video = True
        self.first_input = first_input  # whose metadata is Timeline.metadata
        self.static_metadata = {}  # AudioClip inputs: sample rate, duration...

    def _write_position(self, frame: int, own: Optional[Tuple[Any, Dict[str, Any]]] = None) -> None:
        from interactive_pipe.core.context import _user_context

        user_context = _user_context.get()
        if user_context is None:
            return
        previous = user_context.get(CONTEXT_KEY)
        # the frame filters of the other inputs ran (or run) at the same position
        inputs_metadata = dict(previous.inputs_metadata) if isinstance(previous, Timeline) else {}
        inputs_metadata.update(self.static_metadata)
        if own is not None:
            inputs_metadata[own[0]] = own[1]
        user_context[CONTEXT_KEY] = Timeline(
            frame=frame,
            n_frames=self.timeline_frames,
            fps=self.timeline_fps,
            metadata=inputs_metadata.get(self.first_input, {}),
            inputs_metadata=inputs_metadata,
            has_video=self.has_video,
        )


class VideoFrameFilter(_PositionWriter, FilterCore):
    """Reads frame ``frame_index`` of the ``Video`` buffer ``input_name`` and replaces the buffer with it."""

    def __init__(self, input_name: Any, name: str) -> None:
        self.input_name = input_name
        self._init_position(input_name)
        super().__init__(name=name, inputs=[input_name], outputs=[input_name])

    def apply(self, video: Any, frame_index: int = 0) -> Any:  # type: ignore[override]
        if not isinstance(video, Video):
            raise TypeError(f"input '{self.input_name}' is not a Video anymore (got {type(video).__name__})")
        frame = int(frame_index)
        index = frame_of_video(video, frame, self.timeline_fps)  # several videos: matched by time
        frames = video[index]
        self._write_position(frame, (self.input_name, video.metadata(index)))
        return frames


class GeneratedVideoFrameFilter(VideoFrameFilter):
    """Frame filter placed right after a filter returning a ``Video`` (a video made inside the pipeline).

    Same job as the frame filter of a ``Video`` input: the filters after it
    receive the current frame, and moving the playhead re-runs it (and what
    reads its output), never the filter that made the video. When that filter
    stops returning a ``Video``, its output goes through unchanged.
    """

    def apply(self, video: Any, frame_index: int = 0) -> Any:  # type: ignore[override]
        if not isinstance(video, Video):
            return video
        return super().apply(video, frame_index)


class TimelineClockFilter(_PositionWriter, FilterCore):
    """Writes the position of a timeline without video in ``context["timeline"]`` (no input, no output).

    ``cache_transparent``: with ``cache=True`` a new position does not make
    the engine recompute the filters after it (only this one runs); with
    ``cache="graph"`` the filters reading ``context["timeline"]`` recompute.
    """

    cache_transparent = True

    def __init__(self, name: str = CLOCK_FILTER_NAME) -> None:
        self._init_position(None)
        super().__init__(name=name, inputs=[], outputs=[])

    def apply(self, frame_index: int = 0) -> None:  # type: ignore[override]
        self._write_position(int(frame_index))


class AudioClipFilter(FilterCore):
    """Replaces the ``AudioClip`` buffer ``input_name`` with its signal (independent of the playhead).

    ``plays``: hand the signal to the ``audio`` player (``audio.set``,
    keeping the position); a filter calling ``audio.set`` after it replaces
    the sound, in the same run.
    """

    def __init__(self, input_name: Any, name: str) -> None:
        self.input_name = input_name
        self.plays = False
        super().__init__(name=name, inputs=[input_name], outputs=[input_name])

    def apply(self, clip: Any) -> Any:  # type: ignore[override]
        if not isinstance(clip, AudioClip):
            raise TypeError(f"input '{self.input_name}' is not an AudioClip anymore (got {type(clip).__name__})")
        if self.plays and clip.play:
            from interactive_pipe.core.context import audio

            audio.set(clip.signal, clip.sample_rate, keep_position=True)
        return clip.signal


def timeline_of(pipeline: Any) -> Optional[TimelineControl]:
    """The pipeline's timeline (None when no input is a ``Video`` or an ``AudioClip``)."""
    for ctrl in getattr(pipeline, "controls", None) or []:
        if isinstance(ctrl, TimelineControl):
            return ctrl
    return None


def is_timeline_input(value: Any) -> bool:
    """A ``Video`` or an ``AudioClip``: an input bringing the timeline."""
    return isinstance(value, (Video, AudioClip))


def media_in(inputs_routing: Sequence[Any], values: Any) -> Dict[Any, Any]:
    """``{input name: Video or AudioClip}`` among pipeline inputs given positionally (list) or by name (dict)."""
    if values is None:
        return {}
    if isinstance(values, dict):
        return {name: value for name, value in values.items() if is_timeline_input(value)}
    if not isinstance(values, (list, tuple)):
        values = [values]
    return {name: value for name, value in zip(inputs_routing or [], values) if is_timeline_input(value)}


def videos_in(inputs_routing: Sequence[Any], values: Any) -> Dict[Any, Video]:
    """``{input name: Video}`` among pipeline inputs given positionally (list) or by name (dict)."""
    return {name: value for name, value in media_in(inputs_routing, values).items() if isinstance(value, Video)}


def _free_name(wanted: str, taken: set) -> str:
    name, suffix = wanted, 1
    while name in taken:
        name = f"{wanted}_{suffix}"
        suffix += 1
    return name


def _duration(media: Any) -> float:
    return media.duration if isinstance(media, AudioClip) else len(media) / media.fps


def _is_front_filter(filt: Any) -> bool:
    """A filter ``install_timeline`` puts in front of the pipeline (inputs), not a generated video's."""
    return isinstance(filt, (VideoFrameFilter, AudioClipFilter, TimelineClockFilter)) and not isinstance(
        filt, GeneratedVideoFrameFilter
    )


def generated_videos(pipeline: Any) -> Dict[Any, Video]:
    """``{output name: Video}`` returned by filters of the pipeline (last run), in pipeline order."""
    return pipeline.__dict__.setdefault("_generated_videos", {})


def install_timeline(
    pipeline: "HeadlessPipeline", media: Dict[Any, Any], reset_cache: bool = True
) -> Optional[TimelineControl]:
    """Put a filter in front of the pipeline for every ``Video`` / ``AudioClip`` input, all on one timeline.

    Idempotent; called whenever inputs are given, and when a filter returns a
    ``Video`` (``adopt_generated_videos``, which already put its frame filter
    after that filter). Inputs that are no longer a ``Video`` / ``AudioClip``
    lose their filter. Returns the timeline (None without such an input or a
    generated video). The timeline runs at the first video's frame rate
    (``AUDIO_TIMELINE_FPS`` with sounds only) and lasts as long as the
    longest one. ``reset_cache=False``: called during a run, the cached
    results stay (the new filters start without a result anyway).
    """
    if getattr(pipeline, "controls", None) is None:
        pipeline.controls = []
    installed = [filt for filt in pipeline.filters if _is_front_filter(filt)]
    generated = generated_videos(pipeline)
    timeline = timeline_of(pipeline)
    if not media and not installed and not generated:
        return None
    changed = False
    videos = {name: value for name, value in media.items() if isinstance(value, Video)}
    clips = {name: value for name, value in media.items() if isinstance(value, AudioClip)}
    for filt in installed:
        keep = (
            (isinstance(filt, VideoFrameFilter) and filt.input_name in videos)
            or (isinstance(filt, AudioClipFilter) and filt.input_name in clips)
            or (isinstance(filt, TimelineClockFilter) and clips and not videos)
        )
        if not keep:
            pipeline.filters.remove(filt)
            changed = True
    if not media and not generated:
        if timeline is not None:
            pipeline.controls.remove(timeline)
        user_context = getattr(pipeline, "_user_context", None)
        if user_context is not None:
            user_context.pop(CONTEXT_KEY, None)  # no stale position for the filters
        pipeline.reset_cache()
        return None
    routing = list(pipeline.inputs_routing or [])
    ordered_inputs = sorted(media, key=lambda name: routing.index(name) if name in routing else len(routing))
    # inputs first, then the videos made by filters (in pipeline order): one lane each
    everything = {**{name: media[name] for name in ordered_inputs}, **generated}
    ordered = list(everything)
    all_videos = {name: value for name, value in everything.items() if isinstance(value, Video)}
    first = everything[ordered[0]]
    ordered_videos = [name for name in ordered if name in all_videos]
    fps = all_videos[ordered_videos[0]].fps if ordered_videos else AUDIO_TIMELINE_FPS
    # long enough for every input at the timeline frame rate
    n_frames = max(1, *(int(math.ceil(_duration(value) * fps - 1e-6)) for value in everything.values()))
    if ordered_videos:
        master = all_videos[ordered_videos[0]]
        n_frames = max(n_frames, len(master))
    display = first.timeline_display
    if timeline is None:
        taken_parameters = {name for filt in pipeline.filters for name in (getattr(filt, "values", None) or {})}
        taken_controls = {ctrl.name for ctrl in pipeline.controls}
        name = TIMELINE_NAME if TIMELINE_NAME not in taken_parameters | taken_controls else FALLBACK_TIMELINE_NAME
        timeline = TimelineControl(n_frames, fps=fps, name=_free_name(name, taken_controls), display=display)
        pipeline.controls.insert(0, timeline)
        changed = True
    else:
        timeline.set_length(n_frames, fps)
        timeline.set_display(display)
    timeline.videos = [all_videos[name] for name in ordered_videos]
    timeline.audio_clips = [clips[name] for name in ordered if name in clips]
    timeline.track_names = list(ordered)
    timeline._tracks = [(name, everything[name]) for name in ordered]
    if not timeline.videos:
        timeline.tooltip = "timeline: space plays / pauses, ← → step"

    taken_filters = {filt.name for filt in pipeline.filters}
    existing = {
        (type(filt), getattr(filt, "input_name", None)): filt for filt in pipeline.filters if _is_front_filter(filt)
    }
    front: List[Any] = []
    if clips and not all_videos:  # sounds only: a clock writes the position
        clock = existing.get((TimelineClockFilter, None))
        if clock is None:
            clock = TimelineClockFilter(_free_name(CLOCK_FILTER_NAME, taken_filters))
            changed = True
        front.append(clock)
    first_clip = next((name for name in ordered if name in clips and clips[name].play), None)
    for input_name in ordered_inputs:
        filt: Any
        if input_name in videos:
            filt = existing.get((VideoFrameFilter, input_name))
            if filt is None:
                filt = VideoFrameFilter(input_name, _free_name(f"{FRAME_FILTER_PREFIX}{input_name}", taken_filters))
                changed = True
        else:
            filt = existing.get((AudioClipFilter, input_name))
            if filt is None:
                filt = AudioClipFilter(input_name, _free_name(f"{AUDIO_FILTER_PREFIX}{input_name}", taken_filters))
                changed = True
            filt.plays = input_name == first_clip  # the first clip plays unless a filter sets another sound
        taken_filters.add(filt.name)
        front.append(filt)
    # the frame filters of generated videos stay where they are: right after the filter making the video
    in_place = [
        filt
        for filt in pipeline.filters
        if isinstance(filt, GeneratedVideoFrameFilter) and filt.input_name in generated
    ]
    static_metadata = {name: clips[name].metadata() for name in ordered if name in clips}
    for filt in front + in_place:
        filt.global_params = pipeline.global_params
        filt.framework_state = pipeline.framework_state
        if isinstance(filt, _PositionWriter):
            filt.timeline_fps = timeline.fps
            filt.timeline_frames = timeline.n_frames
            filt.has_video = timeline.has_video
            filt.first_input = ordered[0]
            filt.static_metadata = static_metadata
    # our filters first, in input order (the clock before them)
    others = [filt for filt in pipeline.filters if not _is_front_filter(filt)]
    if [id(f) for f in pipeline.filters[: len(front)]] != [id(f) for f in front]:
        changed = True
        pipeline.filters[:] = front + others
    # one widget drives every filter following the playhead (targets rebuilt in input order)
    driven: List[Any] = [filt for filt in front + in_place if isinstance(filt, _PositionWriter)]
    timeline.filter_to_connect = None
    timeline.__dict__.pop("_extra_targets", None)  # rebuilt below, not appended to the previous ones
    for filt in driven:
        timeline._add_target(filt, FRAME_PARAMETER)
        filt.values = {FRAME_PARAMETER: timeline.value}
    if changed:
        logging.debug(f"timeline {timeline!r} drives {[filt.name for filt in driven]}")
        if reset_cache:
            pipeline.reset_cache()
        engine = getattr(pipeline, "engine", None)
        if clips and engine is not None and not engine.cache:
            logging.warning(
                f"pipeline '{pipeline.name}': AudioClip input with cache=False, so every filter runs again "
                'each time the playhead moves (30 times a second while playing). Pass cache="graph": '
                "the audio filters then run when their sliders move, the filters reading "
                'context["timeline"] when the playhead moves.'
            )
    return timeline


def _input_media(pipeline: Any) -> Dict[Any, Any]:
    """``{input name: Video or AudioClip}`` among the inputs last given to the pipeline."""
    given = getattr(pipeline, "_PipelineCore__inputs", None) or {}
    return {name: value for name, value in given.items() if is_timeline_input(value)}


def adopt_generated_videos(pipeline: Any, filters: List[Any], idx: int, producer: Any, outputs: Dict[Any, Any]) -> bool:
    """Engine hook (``PipelineEngine.output_hook``): a filter returned a ``Video``.

    The first time, a ``GeneratedVideoFrameFilter`` goes in ``filters`` right
    after ``producer`` (same buffer name: the filters reading the output get
    the current frame), and the pipeline gets the timeline if it had none.
    Every time the filter returns a new ``Video`` (its sliders moved), the
    timeline follows: length, frame rate, film strip. Returns True when
    filters were inserted (the engine goes on through them in this run).
    """
    if isinstance(producer, (_PositionWriter, AudioClipFilter)):
        return False
    videos = {name: value for name, value in outputs.items() if isinstance(value, Video)}
    if not videos:
        return False
    generated = generated_videos(pipeline)
    inserted = False
    taken = {filt.name for filt in filters}
    position = idx + 1
    for name, video in videos.items():
        following = filters[position] if position < len(filters) else None
        if not (isinstance(following, GeneratedVideoFrameFilter) and following.input_name == name):
            frame_filter = GeneratedVideoFrameFilter(name, _free_name(f"{FRAME_FILTER_PREFIX}{name}", taken))
            taken.add(frame_filter.name)
            filters.insert(position, frame_filter)
            inserted = True
        position += 1
    if not inserted and all(generated.get(name) is video for name, video in videos.items()):
        return False  # served from the cache: the timeline already knows these videos
    generated.update(videos)
    install_timeline(pipeline, _input_media(pipeline), reset_cache=False)
    return inserted


def install_videos(pipeline: "HeadlessPipeline", videos: Dict[Any, Any]) -> Optional[TimelineControl]:
    """Former name of ``install_timeline`` (``Video`` and ``AudioClip`` inputs)."""
    return install_timeline(pipeline, videos)
