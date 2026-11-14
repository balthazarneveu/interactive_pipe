"""Clean context API using contextvars to avoid polluting function signatures.

This module provides four main exports:
- layout: Display control (titles, styles, grid arrangement)
- audio: Audio playback control
- events: Read-only access to key-bound context events
- get_context(): User-defined shared state between filters

Internal implementation uses contextvars to maintain separate framework and user contexts.
"""

import logging
import numbers
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Union

from interactive_pipe.core.framework_state import FrameworkState

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


def _get_framework_state() -> FrameworkState:
    """Internal: Get the typed framework state.

    Raises:
        RuntimeError: If called outside of filter execution context.
    """
    state = _framework_state.get()
    if state is None:
        raise RuntimeError(
            "Framework operation called outside of filter execution. "
            "This function must be called from within a filter decorated with @interactive "
            "and executed through an interactive pipeline."
        )
    return state


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
    "unit",
    "dpi",
    "xlabel",
    "ylabel",
)
_warned_style_keys: set = set()  # warn once per unknown key: layout.style runs on every frame


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

    def style(self, name: str, *, title: Optional[str] = None, **style_kwargs: Any) -> None:
        """Set display properties for an output.

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
                - ``unit``: text appended to the colorbar labels (``"dB"``).
                - ``dpi``: resolution used to rasterise a matplotlib figure
                  output (default 120).

                NaN and masked (``numpy.ma``) values of a styled 2D array are
                shown in magenta; ``±inf`` go to the ends of the scale.
                - ``xlabel`` / ``ylabel``: axis labels (matplotlib backend only;
                  for curves prefer ``Curve(..., xlabel=...)``).

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
        state = _get_framework_state()

        style = {}
        if title is not None:
            style["title"] = title
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
        style.update(style_kwargs)
        subtitle = style_kwargs.get("subtitle")
        if subtitle:
            # backends show a single title line: the subtitle goes after it
            style["title"] = f"{title if title is not None else name} · {subtitle}"

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
        state = _get_framework_state()
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


class _AudioProxy:
    """Proxy for audio playback control using contextvars.

    This class provides a clean API for controlling audio playback
    without polluting function signatures with global_params.
    """

    def set(self, audio_path: str) -> None:
        """Set the audio file to play.

        Args:
            audio_path: Path to the audio file

        Example:
            ```python
            audio.set("path/to/track.mp3")
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        # AudioBindings defaults to no-ops, so this silently does nothing
        # outside a GUI (same behavior as before)
        state.audio.set_audio(audio_path)

    def play(self) -> None:
        """Start audio playback.

        Example:
            ```python
            audio.play()
            ```

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
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
        state = _get_framework_state()
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
        state = _get_framework_state()
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
        state = _get_framework_state()
        self._record_read(state, name)
        return state.events[name]

    def get(self, name: str, default: bool = False) -> bool:
        """Return the event flag, or `default` when the event is not bound.

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        self._record_read(state, name)
        return state.events.get(name, default)

    def __contains__(self, name: str) -> bool:
        """Check whether an event name is bound."""
        state = _get_framework_state()
        self._record_read(state, name)
        return name in state.events

    def keys(self):
        """Names of all bound events (registers the filter as a reader of each)."""
        state = _get_framework_state()
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
    ctx = _user_context.get()
    if ctx is None:
        raise RuntimeError(
            "get_context() called outside of pipeline execution. "
            "This function must be called from within a filter executed through an interactive pipeline."
        )
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
        return get_context()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Set item in context using dict-style access."""
        get_context()[key] = value

    def __getattr__(self, name: str) -> Any:
        """Get item from context using attribute-style access."""
        if name.startswith("_"):
            # dunder/private lookups come from Python internals and tooling
            # (copy, pickle, IPython completion...), never from user context keys
            raise AttributeError(name)
        try:
            return get_context()[name]
        except KeyError:
            raise AttributeError(
                f"Context has no attribute '{name}'. Available keys: {list(get_context().keys())}"
            ) from None

    def __setattr__(self, name: str, value: Any) -> None:
        """Set item in context using attribute-style access."""
        get_context()[name] = value

    def __delitem__(self, key: str) -> None:
        """Delete item from context."""
        del get_context()[key]

    def __contains__(self, key: str) -> bool:
        """Check if key exists in context."""
        return key in get_context()

    def get(self, key: str, default: Any = None) -> Any:
        """Get item from context with default value."""
        return get_context().get(key, default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Set default value if key doesn't exist."""
        return get_context().setdefault(key, default)

    def pop(self, key: str, *args) -> Any:
        """Pop item from context."""
        return get_context().pop(key, *args)

    def keys(self):
        """Get context keys."""
        return get_context().keys()

    def values(self):
        """Get context values."""
        return get_context().values()

    def items(self):
        """Get context items."""
        return get_context().items()

    def update(self, *args, **kwargs) -> None:
        """Update context with dict or kwargs."""
        get_context().update(*args, **kwargs)

    def clear(self) -> None:
        """Clear context."""
        get_context().clear()

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
