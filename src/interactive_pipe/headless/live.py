"""Webcam inputs: the live clock and the frame filters a pipeline installs for them.

A pipeline input given as a ``Webcam`` is not handed to the filters: the
pipeline puts a small *frame filter* in front of them (``webcam_<input>``,
writing the latest camera frame in place of the ``Webcam``) and a
``LiveControl`` clock drives every frame filter. The clock is a
``TimeControl``: the Qt and Dear PyGui windows tick it ``fps`` times per
second (each tick shows a new frame) and its pause key freezes the feed.

Headless runs (``pipe.headless``, ``snapshot``, ``sweep``) and the backends
without a timer read one new frame per run.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

from interactive_pipe.core.filter import FilterCore
from interactive_pipe.data_objects.webcam import Webcam
from interactive_pipe.headless.control import TimeControl

if TYPE_CHECKING:
    from interactive_pipe.headless.pipeline import HeadlessPipeline

#: control name of the live clock ("live_feed" when a filter parameter already uses it)
LIVE_NAME = "live"
FALLBACK_LIVE_NAME = "live_feed"
FRAME_FILTER_PREFIX = "webcam_"
#: parameter of the frame filters driven by the clock
TICK_PARAMETER = "live_tick"


class LiveControl(TimeControl):
    """Clock of the ``Webcam`` inputs of a pipeline (seconds since the window opened).

    Created by the pipeline when an input is a ``Webcam``: you do not declare
    it. The Qt and Dear PyGui windows tick it (a new frame each tick, no
    widget); its pause key (<kbd>Space</kbd> by default) freezes the feed.
    Other backends show no widget and read a new frame on every run.

    Attributes:
        ticking: a window's timer drives it (frames come from the background
            reader, and a frozen clock keeps the same frame); False headless.
        webcams: the ``Webcam`` inputs it drives.
    """

    def __init__(self, fps: float, name: str = LIVE_NAME, freeze_key: str = " ") -> None:
        super().__init__(
            name=name,
            update_interval_ms=max(int(round(1000.0 / fps)), 1),
            pause_resume_key=freeze_key,
            tooltip="live camera feed: space freezes / unfreezes it",
        )
        self.value_range = [0.0, 1e12]  # runs for ever (TimeControl stops at one hour)
        self.ticking = False
        self.webcams: list = []

    def __repr__(self) -> str:
        return f"LiveControl({self.name!r}, every {self.update_interval_ms} ms)"


class WebcamFrameFilter(FilterCore):
    """Replaces the ``Webcam`` buffer ``input_name`` with a camera frame.

    Never cached by the engine (a new frame must reach the filters after it):
    it keeps the frame of the current clock tick itself, so a slider moved on
    a frozen feed processes the frozen frame.
    """

    def __init__(self, input_name: Any, name: str, clock: LiveControl) -> None:
        self.input_name = input_name
        self.clock = clock
        self._tick: Optional[float] = None
        self._frame: Any = None
        super().__init__(name=name, inputs=[input_name], outputs=[input_name], cache=False)

    def apply(self, webcam: Any, live_tick: float = 0.0) -> Any:  # type: ignore[override]
        if not isinstance(webcam, Webcam):
            raise TypeError(f"input '{self.input_name}' is not a Webcam anymore (got {type(webcam).__name__})")
        if not self.clock.ticking:
            return webcam.read()  # headless: one new frame per run
        if self._frame is None or live_tick != self._tick:
            self._frame = webcam.latest()
            self._tick = live_tick
        return self._frame

    def reset_cache(self) -> None:
        self.cache = False  # whatever the pipeline asks: see the class docstring
        super().reset_cache()


def live_clock_of(pipeline: Any) -> Optional[LiveControl]:
    """The pipeline's live clock (None when no input is a ``Webcam``)."""
    for ctrl in getattr(pipeline, "controls", None) or []:
        if isinstance(ctrl, LiveControl):
            return ctrl
    return None


def webcams_in(inputs_routing: Sequence[Any], values: Any) -> Dict[Any, Webcam]:
    """``{input name: Webcam}`` among pipeline inputs given positionally (list) or by name (dict)."""
    if values is None:
        return {}
    if isinstance(values, dict):
        return {name: value for name, value in values.items() if isinstance(value, Webcam)}
    if not isinstance(values, (list, tuple)):
        values = [values]
    return {name: value for name, value in zip(inputs_routing or [], values) if isinstance(value, Webcam)}


def _free_name(wanted: str, taken: set) -> str:
    name, suffix = wanted, 1
    while name in taken:
        name = f"{wanted}_{suffix}"
        suffix += 1
    return name


def install_webcams(pipeline: "HeadlessPipeline", webcams: Dict[Any, Webcam]) -> Optional[LiveControl]:
    """Put a frame filter in front of the pipeline for every ``Webcam`` input, all driven by one clock.

    Idempotent; called whenever inputs are given. Inputs that are no longer a
    ``Webcam`` lose their frame filter. Returns the clock (None without webcam).
    """
    if getattr(pipeline, "controls", None) is None:
        pipeline.controls = []
    frame_filters = {filt.input_name: filt for filt in pipeline.filters if isinstance(filt, WebcamFrameFilter)}
    clock = live_clock_of(pipeline)
    if not webcams and not frame_filters:
        return None
    for input_name, filt in list(frame_filters.items()):
        if input_name not in webcams:
            pipeline.filters.remove(filt)
            del frame_filters[input_name]
    if not webcams:
        if clock is not None:
            pipeline.controls.remove(clock)
        pipeline.reset_cache()
        return None
    routing = list(pipeline.inputs_routing or [])
    ordered = sorted(webcams, key=lambda name: routing.index(name) if name in routing else len(routing))
    first = webcams[ordered[0]]
    if clock is None:
        taken_parameters = {name for filt in pipeline.filters for name in (getattr(filt, "values", None) or {})}
        taken_controls = {ctrl.name for ctrl in pipeline.controls}
        name = LIVE_NAME if LIVE_NAME not in taken_parameters | taken_controls else FALLBACK_LIVE_NAME
        clock = LiveControl(first.fps, name=_free_name(name, taken_controls), freeze_key=first.freeze_key)
        pipeline.controls.append(clock)
    taken_filters = {filt.name for filt in pipeline.filters}
    new_filters = []
    for input_name in ordered:
        if input_name in frame_filters:
            continue
        filt = WebcamFrameFilter(input_name, _free_name(f"{FRAME_FILTER_PREFIX}{input_name}", taken_filters), clock)
        taken_filters.add(filt.name)
        filt.global_params = pipeline.global_params
        filt.framework_state = pipeline.framework_state
        new_filters.append(filt)
    if new_filters:
        pipeline.filters[0:0] = new_filters
        logging.debug(f"{clock!r} drives {[filt.name for filt in new_filters]}")
    clock.filter_to_connect = None
    clock.__dict__["_extra_targets"] = []
    for filt in pipeline.filters:
        if isinstance(filt, WebcamFrameFilter):
            filt.clock = clock
            clock._add_target(filt, TICK_PARAMETER)
            filt.values = {TICK_PARAMETER: clock.value}
    clock.webcams = [webcams[name] for name in ordered]
    if new_filters:
        pipeline.reset_cache()
    return clock
