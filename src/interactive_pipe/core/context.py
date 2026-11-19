"""Clean context API using contextvars to avoid polluting function signatures.

This module provides four main exports:
- layout: Display control (titles, styles, grid arrangement)
- audio: Audio playback control
- events: Read-only access to key-bound context events
- get_context(): User-defined shared state between filters

Internal implementation uses contextvars to maintain separate framework and user contexts.
"""

import atexit
import logging
import numbers
import os
import tempfile
import wave
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional, Union

import numpy as np

from interactive_pipe.core.audio_mixer import to_float_frames
from interactive_pipe.core.framework_state import AudioRequest, FrameworkState
from interactive_pipe.core.framework_state import _noop as _NO_AUDIO

# ============================================================================
# Internal Context Variables (not exported)
# ============================================================================

_framework_state: ContextVar[Optional[FrameworkState]] = ContextVar("_ip_framework_state", default=None)

_user_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("_ip_user_context", default=None)

# name of the filter currently executing (set by filter.run), used to attribute
# event reads to filters
_current_filter: ContextVar[Optional[str]] = ContextVar("_ip_current_filter", default=None)


# ============================================================================
# Internal Helper Functions (not exported)
# ============================================================================


def _outside_message(operation: str, scope: str) -> str:
    """Error for a framework call made outside a running filter: which call,
    and the fix (the two lines that put it inside a filter)."""
    return (
        f"{operation} called outside of {scope} execution: it only works inside an @interactive filter "
        "(run by a pipeline, or called directly like a plain function: then layout / audio calls do "
        "nothing and the context is a scratch dict). Move the call into a filter:\n\n"
        "    @interactive()\n"
        "    def my_filter(img):\n"
        f"        {operation}\n"
        "        return img\n"
    )


def _get_framework_state(operation: str = "This framework operation") -> FrameworkState:
    """Internal: Get the typed framework state.

    ``operation``: the user call (``layout.style('out', ...)``), named in the error.

    Raises:
        RuntimeError: If called outside of filter execution context.
    """
    state = _framework_state.get()
    if state is None:
        raise RuntimeError(_outside_message(operation, "filter"))
    return state


class _DirectCallContext(dict):
    """Scratch context of a filter called directly (outside any pipeline run)."""

    def __init__(self, filter_name: str) -> None:
        super().__init__()
        self._filter_name = filter_name

    def __missing__(self, key: Any) -> Any:
        raise KeyError(
            f"context[{key!r}] is not set: '{self._filter_name}' is called directly (not by a pipeline), "
            "so its context starts empty - in a pipeline, an earlier filter would have written it. "
            f"Use context.get({key!r}, default) in the filter, or test it inside a pipeline."
        )


@contextmanager
def direct_call_scope(filter_name: str) -> Iterator[None]:
    """Let an ``@interactive`` filter run when called directly, like a plain function.

    Outside a pipeline run (a unit test calling ``compare(out, gt)``), the call
    gets a throwaway framework state and an empty scratch context:
    ``layout.style`` / ``layout.grid`` and ``audio`` calls are validated then
    do nothing, ``events.get(name)`` returns its default, ``context`` writes
    are kept for the duration of the call only, and reading a key nobody wrote
    raises a ``KeyError`` saying so. Inside a pipeline run (also a filter
    calling another decorated filter) nothing changes.
    """
    if _framework_state.get() is not None or _user_context.get() is not None:
        yield
        return
    state_token = _framework_state.set(FrameworkState())
    context_token = _user_context.set(_DirectCallContext(filter_name))
    try:
        yield
    finally:
        _user_context.reset(context_token)
        _framework_state.reset(state_token)


def _set_framework_state(state: Optional[FrameworkState]) -> None:
    """Internal: Set framework state (called by filter.run)."""
    _framework_state.set(state)


def _set_user_context(ctx: Optional[Dict[str, Any]]) -> None:
    """Internal: Set user context (called by pipeline)."""
    _user_context.set(ctx)


def _set_current_filter(name: Optional[str]) -> None:
    """Internal: Set the name of the running filter (called by filter.run)."""
    _current_filter.set(name)


# ============================================================================
# Layout Proxy - Display Control
# ============================================================================


SUPPORTED_STYLE_KEYS = (
    "title",
    "subtitle",
    "colormap",
    "vmin",
    "vmax",
    "center",
    "colorbar",
    "label",
    "unit",
    "dpi",
    "xlabel",
    "ylabel",
    "extent",
)
_warned_style_keys: set = set()  # warn once per unknown key: layout.style runs on every frame
_UNSET: Any = object()  # layout.style(title=...) not given (an explicit None removes the title)


def _check_extent(name: str, extent: Any) -> None:
    if extent is None:
        return
    if (
        not isinstance(extent, (tuple, list))
        or len(extent) != 4
        or any(isinstance(v, bool) or not isinstance(v, numbers.Real) for v in extent)
    ):
        raise TypeError(
            f"layout.style('{name}', extent=...): (x0, x1, y0, y1) numbers are expected "
            f"(x of the left / right columns, y of the bottom / top rows), got {extent!r}"
        )


def _check_colormap_name(colormap: str) -> None:
    import matplotlib

    if colormap not in matplotlib.colormaps:
        import difflib

        matches = difflib.get_close_matches(colormap, list(matplotlib.colormaps), n=3)
        hint = f" Did you mean {', '.join(repr(match) for match in matches)}?" if matches else ""
        raise ValueError(f"layout.style: unknown colormap {colormap!r}.{hint}")


class _LayoutProxy:
    """Proxy for display and layout operations using contextvars.

    This class provides a clean API for controlling output display properties
    and grid arrangements without polluting function signatures.

    Available methods:
        - style(): Set display properties (title, colormap, etc.)
        - grid(): Set the output grid layout
        - row(): Convenience for single-row layout
    """

    def style(self, name: str, *, title: Any = _UNSET, **style_kwargs: Any) -> None:
        """Set display properties for an output.

        Calls on one output during one run add up: a later call changes only
        the keys it gives (``layout.style("h", colormap="viridis")`` then
        ``layout.style("h", title=f"max {m:.1f}")`` keeps the colormap);
        ``key=None`` removes that key. The first call of the next run starts
        from nothing again.

        Args:
            name: Output variable name (must match the variable name in the return statement)
            title: Display title for the output
            **style_kwargs: Additional style properties:

                - ``subtitle``: secondary text, appended to the title
                  (``"title · subtitle"``) on every backend.
                - ``colormap``: matplotlib colormap name (e.g. ``"viridis"``)
                  or ``Colormap`` used to display a 2D ``(H, W)`` array as a
                  heatmap, on every backend.
                - ``vmin`` / ``vmax``: values mapped to the bottom / top of the
                  colormap (or to black / white without a colormap) for 2D
                  arrays; each defaults to the data min / max, as in matplotlib.
                - ``center``: widen the range to be symmetric around this value
                  (diverging data: ``colormap="RdBu", center=0``).
                - ``colorbar``: ``True`` draws the scale (min, max and round
                  ticks) to the right of a 2D array, inside the displayed image,
                  so it looks the same on every backend and in snapshots.
                  ``colorbar="log10 |F|"`` also writes that text vertically
                  along the bar.
                - ``label``: the same text along the bar, with ``colorbar=True``.
                - ``unit``: short unit written once, above the colorbar (``"dB"``).
                - ``dpi``: pixels per inch of a matplotlib figure output: 100
                  in a window cell (where the figure fits the cell, its text
                  the size of a ``Curve``'s), the snapshot's dpi in
                  snapshots, 120 elsewhere.

                NaN and masked (``numpy.ma``) values of a styled 2D array are
                shown in magenta; ``±inf`` go to the ends of the scale.
                - ``extent``: ``(x0, x1, y0, y1)``, the coordinates of the left /
                  right columns and bottom / top rows of a 2D array (as in
                  ``imshow``): the heatmap gets axes with round ticks drawn
                  into the displayed image (every backend and snapshots; the
                  Qt readout then also shows these coordinates). ``extent``
                  alone makes a 2D array a heatmap (data range, gray).
                - ``xlabel`` / ``ylabel``: axis labels; on a heatmap they are
                  drawn with its axes (pixel indices without ``extent``),
                  elsewhere only by the matplotlib backend. For curves use
                  ``Curve(..., xlabel=...)``.

                Other keys are ignored, with a warning.

        Example:
            ```python
            layout.style("processed", title=f"Brightness: {brightness:.2f}")
            layout.style("heatmap", title="Heat Map", colormap="viridis", vmin=0, vmax=1)
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
            ValueError: If ``colormap`` is not a known matplotlib colormap.
        """
        state = _get_framework_state(f"layout.style({name!r}, ...)")

        if title is not _UNSET:
            style_kwargs = {"title": title, **style_kwargs}
        unknown = sorted(key for key in style_kwargs if key not in SUPPORTED_STYLE_KEYS)
        for key in unknown:
            if key not in _warned_style_keys:
                _warned_style_keys.add(key)
                logging.warning(
                    f"layout.style('{name}', {key}=...): unknown style key '{key}' is ignored. "
                    f"Supported keys: {', '.join(SUPPORTED_STYLE_KEYS)}"
                )
        colormap = style_kwargs.get("colormap")
        if isinstance(colormap, str):
            _check_colormap_name(colormap)
        for key in ("vmin", "vmax", "center", "dpi"):
            value = style_kwargs.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, numbers.Real)):
                raise TypeError(f"layout.style('{name}', {key}=...): a number is expected, got {value!r}")
        _check_extent(name, style_kwargs.get("extent"))

        # successive calls on one output during one run add up (later call
        # wins per key, None removes a key); the first call of a run starts afresh
        previous = state.style_calls.get(name)
        given = dict(previous[1]) if previous is not None and previous[0] == state.run_count else {}
        given.update(style_kwargs)
        given = {key: value for key, value in given.items() if value is not None}
        state.style_calls[name] = (state.run_count, given)

        style = dict(given)
        subtitle = given.get("subtitle")
        if subtitle:
            # backends show a single title line: the subtitle goes after it
            style["title"] = f"{given.get('title', name)} · {subtitle}"
        state.output_styles[name] = style

    def grid(self, arrangement: Union[List[str], List[List[str]]]) -> None:
        """Set the output grid layout.

        Args:
            arrangement: Either a flat list of output names (treated as a single row)
                        or a 2D list of output names defining the grid arrangement

        Example:
            ```python
            # Single row (flat list)
            layout.grid(["img1", "img2", "img3"])

            # Single row (nested list - equivalent to above)
            layout.grid([["img1", "img2", "img3"]])

            # 2x2 grid
            layout.grid([
                ["original", "processed"],
                ["histogram", "stats"]
            ])
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state("layout.grid([...])")
        pipeline = state.pipeline
        if pipeline is not None:
            # Convert flat list to nested list (single row)
            if arrangement and isinstance(arrangement[0], str):
                arrangement = [arrangement]  # type: ignore[list-item]
            pipeline.outputs = arrangement

    def row(self, outputs: List[str]) -> None:
        """Convenience method for single-row layout.

        This is equivalent to calling grid([outputs]).

        Args:
            outputs: List of output names to display in a single row

        Example:
            ```python
            layout.row(["original", "filtered", "result"])
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        self.grid([outputs])


# ============================================================================
# Audio Proxy - Playback Control
# ============================================================================


_temporary_wavs: set = set()  # audio.set(signal, rate) files still on disk, deleted at exit


@atexit.register
def _remove_temporary_wavs() -> None:
    for path in list(_temporary_wavs):
        _remove_wav(path)


def _remove_wav(path: str) -> None:
    _temporary_wavs.discard(path)
    try:
        os.remove(path)
    except OSError:
        pass


def _write_temporary_wav(state: FrameworkState, signal: Any, sample_rate: int) -> str:
    """16-bit PCM WAV of ``signal`` in a new temporary file; the previous one of ``state`` is removed.

    A new name per sound: players cache what they loaded from a path.
    """
    if signal.dtype == np.int16:
        pcm = signal
    else:
        pcm = (np.clip(np.nan_to_num(signal.astype(np.float64)), -1.0, 1.0) * 32767).astype(np.int16)
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    handle, path = tempfile.mkstemp(prefix="interactive_pipe_audio_", suffix=".wav")
    os.close(handle)
    _temporary_wavs.add(path)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(np.ascontiguousarray(pcm).astype("<i2").tobytes())
    if state.audio_file is not None:
        _remove_wav(state.audio_file)
    state.audio_file = path
    return path


class _AudioProxy:
    """Proxy for audio playback control using contextvars.

    This class provides a clean API for controlling audio playback
    without polluting function signatures with global_params.
    """

    def set(
        self,
        audio: Any,
        sample_rate: Optional[int] = None,
        keep_position: Optional[bool] = None,
        loop: bool = False,
    ) -> None:
        """Set the sound the GUI plays: a file, or a signal computed by the filter.

        Two forms:

        - ``audio.set("path/to/track.wav")``: a file path (``str`` or ``Path``).
        - ``audio.set(signal, sample_rate)``: a numpy array, mono ``(n,)`` or
          ``(n, channels)`` with 1 or 2 channels, float in ``[-1, 1]``
          (clipped) or ``int16``; ``sample_rate`` in Hz. The Qt window
          streams it from memory; Gradio gets a temporary WAV file, deleted
          when the next sound replaces it and at exit.

        Each call replaces what is playing; call ``audio.play()`` after it to
        start playback. ``keep_position`` chooses where the new sound starts:

        - ``True``: at the same instant as the previous sound (Qt), so a
          slider tweaking a sound you are listening to does not send you back
          to the start. Signals are swapped sample-accurately with a short
          cross-fade: dragging a slider is heard live, without clicks. A
          position past the new sound's end starts it from the beginning.
        - ``False``: from the beginning.
        - ``None`` (default): ``True`` for a signal (a processed version of
          the same sound), ``False`` for a file (another track).

        ``loop=True`` repeats the sound (Qt). Use ``cache="graph"`` for audio
        pipelines: with the cache off every slider re-runs every filter, the
        one calling ``audio.set`` included. Playback exists in the Qt and
        Gradio windows only: in headless calls, snapshots, sweeps, tests and
        the other backends the call checks its arguments and does nothing
        else (no file, no audio device).

        Example:
            ```python
            audio.set(np.sin(2 * np.pi * 440 * t), 16000, loop=True)
            audio.play()
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
            TypeError: If the arguments match neither form.
        """
        state = _get_framework_state("audio.set(...)")
        if keep_position is not None and not isinstance(keep_position, bool):
            raise TypeError(f"audio.set: keep_position must be True, False or None, got {keep_position!r}")
        if not isinstance(loop, bool):
            raise TypeError(f"audio.set: loop must be True or False, got {loop!r}")
        forms = (
            "audio.set(path) with a file path, or audio.set(signal, sample_rate) with a numpy array "
            "(n,) or (n, channels), float in [-1, 1] or int16, and the rate in Hz"
        )
        bindings = state.audio
        if isinstance(audio, (str, os.PathLike)):
            if sample_rate is not None:
                raise TypeError(f"audio.set: a file has its own sample rate, do not pass one. Use {forms}")
            request = AudioRequest(path=os.fspath(audio), keep_position=bool(keep_position), loop=loop)
        else:
            if not isinstance(audio, np.ndarray):
                raise TypeError(f"audio.set: got {type(audio).__name__}. Use {forms}")
            if sample_rate is None or isinstance(sample_rate, bool) or not isinstance(sample_rate, numbers.Integral):
                raise TypeError(f"audio.set(signal, sample_rate): an integer rate in Hz is expected. Use {forms}")
            if sample_rate <= 0:
                raise ValueError(f"audio.set(signal, sample_rate): the rate must be positive, got {sample_rate}")
            if audio.ndim not in (1, 2) or (audio.ndim == 2 and audio.shape[1] not in (1, 2)):
                hint = " (pass signal.T: channels go last)" if audio.ndim == 2 and audio.shape[0] in (1, 2) else ""
                raise TypeError(f"audio.set: signal of shape {audio.shape}{hint}. Use {forms}")
            if audio.dtype != np.int16 and audio.dtype.kind not in "fiu":
                raise TypeError(f"audio.set: signal of dtype {audio.dtype}. Use {forms}")
            if bindings.set_audio is _NO_AUDIO and bindings.load_audio is None:
                return  # no player (headless, snapshot, a backend without audio): no file either
            keep = keep_position is None or keep_position
            if bindings.load_audio is not None and bindings.accepts_signals:
                request = AudioRequest(
                    signal=to_float_frames(audio), sample_rate=int(sample_rate), keep_position=keep, loop=loop
                )
            else:
                path = _write_temporary_wav(state, audio, int(sample_rate))
                request = AudioRequest(path=path, keep_position=keep, loop=loop)
        # AudioBindings defaults to no-ops: does nothing outside a GUI with audio
        if bindings.load_audio is not None:
            bindings.load_audio(request)
        else:
            bindings.set_audio(request.path)

    def play(self) -> None:
        """Start audio playback.

        Example:
            ```python
            audio.play()
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state("audio.play()")
        state.audio.play()

    def pause(self) -> None:
        """Pause audio playback.

        Example:
            ```python
            audio.pause()
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state("audio.pause()")
        state.audio.pause()

    def stop(self) -> None:
        """Stop audio playback.

        Example:
            ```python
            audio.stop()
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state("audio.stop()")
        state.audio.stop()


# ============================================================================
# Events Proxy - Key-Bound Context Events (read-only)
# ============================================================================


class _EventsProxy:
    """Read-only proxy for key-bound context events.

    GUI backends raise an event flag when a key registered through
    InteractivePipeGUI.bind_key_to_context is pressed; filters read the flags
    here. An event stays True only for the single pipeline run triggered by
    the key press - the GUI resets it right after.

    Example:
        ```python
        from interactive_pipe import events, interactive

        @interactive()
        def denoise(img):
            strength = 0.5 if events.get("boost_denoise") else 0.1
            return smooth(img, strength)
        ```

    Prefer events.get(name): it returns False for events that were never
    bound, so the same filter also runs headless or in a GUI without the
    key binding.
    """

    @staticmethod
    def _record_read(state: FrameworkState, name: str) -> None:
        """Register the running filter as a reader of the event (cache invalidation)."""
        filter_name = _current_filter.get()
        if filter_name is not None:
            state.event_readers.setdefault(name, set()).add(filter_name)

    def __getitem__(self, name: str) -> bool:
        """Strict access: raises KeyError if the event was never bound.

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state(f"events[{name!r}]")
        self._record_read(state, name)
        return state.events[name]

    def get(self, name: str, default: bool = False) -> bool:
        """Return the event flag, or `default` when the event is not bound.

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state(f"events.get({name!r})")
        self._record_read(state, name)
        return state.events.get(name, default)

    def __contains__(self, name: str) -> bool:
        """Check whether an event name is bound."""
        state = _get_framework_state(f"{name!r} in events")
        self._record_read(state, name)
        return name in state.events

    def keys(self):
        """Names of all bound events (registers the filter as a reader of each)."""
        state = _get_framework_state("events.keys()")
        for name in state.events:
            self._record_read(state, name)
        return state.events.keys()

    def __repr__(self) -> str:
        try:
            return f"<EventsProxy: {dict(_get_framework_state().events)}>"
        except RuntimeError:
            return "<EventsProxy: not in filter execution>"


# ============================================================================
# User Context - Shared State Between Filters
# ============================================================================


def get_context() -> Dict[str, Any]:
    """Get shared context for passing data between filters.

    This returns a simple dictionary for user-defined state only.
    Framework internals (keys starting with __) are not accessible here.

    Returns:
        A shared dictionary for user-defined state.

    Raises:
        RuntimeError: If called outside of pipeline execution.

    Example:
        ```python
        # In filter A
        @interactive(threshold=(0.5, [0.0, 1.0]))
        def detect_objects(img, threshold=0.5):
            objects = find_objects(img, threshold)
            ctx = get_context()
            ctx["detected_objects"] = objects
            ctx["detection_count"] = len(objects)
            return img_with_boxes

        # In filter B (runs after A)
        @interactive()
        def analyze_objects(img):
            ctx = get_context()
            objects = ctx.get("detected_objects", [])
            count = ctx.get("detection_count", 0)
            layout.style("analysis", title=f"Found {count} objects")
            return analysis_result
        ```
    """
    return _require_context("ctx = get_context()")


def _require_context(operation: str) -> Dict[str, Any]:
    """The user context, or a RuntimeError naming `operation` and the fix."""
    ctx = _user_context.get()
    if ctx is None:
        raise RuntimeError(_outside_message(operation, "pipeline"))
    return ctx


# ============================================================================
# Context Proxy - Direct dict-like access
# ============================================================================


class _ContextProxy:
    """Proxy object for direct dict-like access to user context.

    This allows using context["key"] or context.key directly instead of
    ctx = get_context(); ctx["key"].

    Example:
        ```python
        from interactive_pipe import context

        @interactive()
        def my_filter(img):
            # Direct dict-style access
            context["my_data"] = value
            other_data = context.get("other_key", default)

            # Or attribute-style access
            context.my_data = value
            other_data = context.other_key

            return img
        ```
    """

    def __getitem__(self, key: str) -> Any:
        """Get item from context using dict-style access."""
        return _require_context(f"context[{key!r}]")[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Set item in context using dict-style access."""
        _require_context(f"context[{key!r}] = ...")[key] = value

    def __getattr__(self, name: str) -> Any:
        """Get item from context using attribute-style access."""
        if name.startswith("_"):
            # dunder/private lookups come from Python internals and tooling
            # (copy, pickle, IPython completion...), never from user context keys
            raise AttributeError(name)
        try:
            return _require_context(f"context.{name}")[name]
        except KeyError:
            raise AttributeError(
                f"Context has no attribute '{name}'. Available keys: {list(get_context().keys())}"
            ) from None

    def __setattr__(self, name: str, value: Any) -> None:
        """Set item in context using attribute-style access."""
        _require_context(f"context.{name} = ...")[name] = value

    def __delitem__(self, key: str) -> None:
        """Delete item from context."""
        del _require_context(f"del context[{key!r}]")[key]

    def __contains__(self, key: str) -> bool:
        """Check if key exists in context."""
        return key in _require_context(f"{key!r} in context")

    def get(self, key: str, default: Any = None) -> Any:
        """Get item from context with default value."""
        return _require_context(f"context.get({key!r})").get(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Set default value if key doesn't exist."""
        return _require_context(f"context.setdefault({key!r}, ...)").setdefault(key, default)

    def pop(self, key: str, *args) -> Any:
        """Pop item from context."""
        return _require_context(f"context.pop({key!r})").pop(key, *args)

    def keys(self):
        """Get context keys."""
        return _require_context("context.keys()").keys()

    def values(self):
        """Get context values."""
        return _require_context("context.values()").values()

    def items(self):
        """Get context items."""
        return _require_context("context.items()").items()

    def update(self, *args, **kwargs) -> None:
        """Update context with dict or kwargs."""
        _require_context("context.update(...)").update(*args, **kwargs)

    def clear(self) -> None:
        """Clear context."""
        _require_context("context.clear()").clear()

    def __repr__(self) -> str:
        """String representation."""
        try:
            return f"<ContextProxy: {get_context()}>"
        except RuntimeError:
            return "<ContextProxy: not in pipeline execution>"


# ============================================================================
# Removed legacy API detection
# ============================================================================

# Historic magic kwarg names that used to trigger implicit dict injection into
# filter functions. Injection was REMOVED in 0.9.0; declaring one of these in a
# filter signature now raises TypeError at filter construction.
REMOVED_CONTEXT_KWARGS = ("global_params", "global_parameters", "global_state", "global_context", "context", "state")

# Removed pipeline-init aliases for the (still supported) `context=` argument.
# NOTE: "context" is deliberately excluded - it is the modern named parameter.
REMOVED_CONTEXT_ALIASES = tuple(key for key in REMOVED_CONTEXT_KWARGS if key != "context")


# ============================================================================
# Module-level instances (exported)
# ============================================================================

layout = _LayoutProxy()
audio = _AudioProxy()
events = _EventsProxy()  # Read-only view of key-bound context events
context = _ContextProxy()  # Direct dict-like access to user context
