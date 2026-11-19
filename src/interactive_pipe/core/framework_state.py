"""Typed framework state shared between the pipeline, filters, GUIs and the
context proxies (layout/audio).

Framework internals live here; pipeline.global_params is the user-facing
shared-state dict for class-based filters and carries no framework state.

This module imports nothing from the rest of core, so anything can import it
without cycles.
"""

import weakref
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Optional, Set, Tuple


def _noop(*_args, **_kwargs) -> None:
    """Default audio binding: silently do nothing outside a GUI."""


@dataclass
class AudioRequest:
    """What ``audio.set(...)`` asks a backend to play.

    Exactly one of ``path`` (a file) and ``signal`` (float32 ``(n, channels)``
    in [-1, 1], with ``sample_rate``) is set; ``signal`` only reaches backends
    declaring ``accepts_signals``, the others get a temporary WAV ``path``.
    """

    path: Optional[str] = None
    signal: Any = None
    sample_rate: Optional[int] = None
    keep_position: bool = False
    loop: bool = False


@dataclass
class AudioBindings:
    """Callbacks a GUI backend registers for the context `audio` proxy.

    ``load_audio(request)`` (an :class:`AudioRequest`) is the full interface:
    position kept or not, looping, and numpy signals passed as they are when
    ``accepts_signals`` is True (no WAV file). Backends providing only
    ``set_audio(path)`` get every sound from its start, as a file.
    """

    set_audio: Callable[[Any], None] = _noop
    load_audio: Optional[Callable[[AudioRequest], None]] = None
    accepts_signals: bool = False
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
        event_readers: event name -> names of the filters that read it through
            the `events` proxy (recorded at runtime, lets a key press invalidate
            only the filters that depend on the event)
        audio: audio playback callbacks registered by the GUI backend
        pipeline: back-reference to the owning pipeline, held via weakref so
            the state never keeps the pipeline (and the GUI) alive.
    """

    output_styles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # layout.style merges the calls made on one output during one run: the
    # run counter (bumped by PipelineCore.run) and, per output, the run of its
    # last style plus the keyword arguments given so far in that run
    run_count: int = 0
    style_calls: Dict[str, Tuple[int, Dict[str, Any]]] = field(default_factory=dict)
    events: Dict[str, bool] = field(default_factory=dict)
    event_readers: Dict[str, Set[str]] = field(default_factory=dict)
    audio: AudioBindings = field(default_factory=AudioBindings)
    # temporary WAV written by audio.set(signal, rate), removed when replaced
    audio_file: Optional[str] = None
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
            event_readers={name: set(readers) for name, readers in self.event_readers.items()},
            audio=replace(self.audio),
        )
        state._pipeline_ref = self._pipeline_ref
        return state

    def restore(self, snapshot: "FrameworkState") -> None:
        """Restore contents in place from a snapshot() result."""
        self.output_styles.clear()
        self.output_styles.update({name: dict(style) for name, style in snapshot.output_styles.items()})
        self.style_calls.clear()
        self.events.clear()
        self.events.update(snapshot.events)
        self.event_readers.clear()
        self.event_readers.update({name: set(readers) for name, readers in snapshot.event_readers.items()})
        self.audio = replace(snapshot.audio)
        self._pipeline_ref = snapshot._pipeline_ref
