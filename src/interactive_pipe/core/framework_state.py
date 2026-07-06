"""Typed framework state shared between the pipeline, filters, GUIs and the
context proxies (layout/audio).

Framework internals live here; pipeline.global_params is the user-facing
shared-state dict for class-based filters and carries no framework state.

This module imports nothing from the rest of core, so anything can import it
without cycles.
"""

import weakref
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


def _noop(*_args, **_kwargs) -> None:
    """Default audio binding: silently do nothing outside a GUI."""


@dataclass
class AudioBindings:
    """Callbacks a GUI backend registers for the context `audio` proxy."""

    set_audio: Callable[[Any], None] = _noop
    play: Callable[[], None] = _noop
    pause: Callable[[], None] = _noop
    stop: Callable[[], None] = _noop


@dataclass
class FrameworkState:
    """Framework-internal state owned by the pipeline (one per pipeline).

    Fields:
        output_styles: display styles per output name (layout.style writes,
            windows read titles from it)
        events: key-bound context events managed by the GUI base class
        audio: audio playback callbacks registered by the GUI backend
        pipeline: back-reference to the owning pipeline, held via weakref so
            the state never keeps the pipeline (and the GUI) alive.
    """

    output_styles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    events: Dict[str, bool] = field(default_factory=dict)
    audio: AudioBindings = field(default_factory=AudioBindings)
    _pipeline_ref: Optional[weakref.ReferenceType] = field(default=None, repr=False)

    @property
    def pipeline(self):
        return self._pipeline_ref() if self._pipeline_ref is not None else None

    @pipeline.setter
    def pipeline(self, pipeline) -> None:
        self._pipeline_ref = weakref.ref(pipeline) if pipeline is not None else None

    def snapshot(self) -> "FrameworkState":
        """Shallow copy: dicts are copied, audio callables kept by reference
        (deep-copying GUI callbacks would break audio playback)."""
        state = FrameworkState(
            output_styles={name: dict(style) for name, style in self.output_styles.items()},
            events=dict(self.events),
            audio=AudioBindings(
                set_audio=self.audio.set_audio,
                play=self.audio.play,
                pause=self.audio.pause,
                stop=self.audio.stop,
            ),
        )
        state._pipeline_ref = self._pipeline_ref
        return state

    def restore(self, snapshot: "FrameworkState") -> None:
        """Restore contents in place from a snapshot() result."""
        self.output_styles.clear()
        self.output_styles.update({name: dict(style) for name, style in snapshot.output_styles.items()})
        self.events.clear()
        self.events.update(snapshot.events)
        self.audio = AudioBindings(
            set_audio=snapshot.audio.set_audio,
            play=snapshot.audio.play,
            pause=snapshot.audio.pause,
            stop=snapshot.audio.stop,
        )
        self._pipeline_ref = snapshot._pipeline_ref
