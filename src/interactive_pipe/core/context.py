"""Clean context API using contextvars to avoid polluting function signatures.

This module provides three main exports:
- layout: Display control (titles, styles, grid arrangement)
- audio: Audio playback control
- get_context(): User-defined shared state between filters

Internal implementation uses contextvars to maintain separate framework and user contexts.
"""

from contextvars import ContextVar
from typing import Dict, Any, Optional, List

# ============================================================================
# Internal Context Variables (not exported)
# ============================================================================

_framework_state: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "_ip_framework_state", default=None
)

_user_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "_ip_user_context", default=None
)


# ============================================================================
# Internal Helper Functions (not exported)
# ============================================================================


def _get_framework_state() -> Dict[str, Any]:
    """Internal: Get framework state dict.

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


def _set_framework_state(state: Optional[Dict[str, Any]]) -> None:
    """Internal: Set framework state (called by filter.run)."""
    _framework_state.set(state)


def _set_user_context(ctx: Optional[Dict[str, Any]]) -> None:
    """Internal: Set user context (called by pipeline)."""
    _user_context.set(ctx)


# ============================================================================
# Layout Proxy - Display Control
# ============================================================================


class _LayoutProxy:
    """Proxy for display and layout operations using contextvars.

    This class provides a clean API for controlling output display properties
    and grid arrangements without polluting function signatures.

    Available methods:
        - style() / set_style(): Set display properties (title, colormap, etc.)
        - grid() / set_grid() / canvas() / set_canvas(): Set the output grid layout
        - row(): Convenience for single-row layout
    """

    def style(self, name: str, *, title: str = None, **style_kwargs) -> None:
        """Set display properties for an output.

        Args:
            name: Output variable name (must match the variable name in the return statement)
            title: Display title for the output
            **style_kwargs: Additional style properties (colormap, vmin, vmax, etc.)

        Example:
            layout.style("processed", title=f"Brightness: {brightness:.2f}")
            layout.style("heatmap", title="Heat Map", colormap="viridis", vmin=0, vmax=1)

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        if "__output_styles" not in state:
            state["__output_styles"] = {}

        style = {}
        if title is not None:
            style["title"] = title
        style.update(style_kwargs)

        state["__output_styles"][name] = style

    def grid(self, arrangement: List[List[str]]) -> None:
        """Set the output grid layout.

        Args:
            arrangement: 2D list of output names defining the grid arrangement

        Example:
            # 2x2 grid
            layout.grid([
                ["original", "processed"],
                ["histogram", "stats"]
            ])

            # Single row (can also use layout.row())
            layout.grid([["img1", "img2", "img3"]])

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        pipeline = state.get("__pipeline")
        if pipeline is not None:
            pipeline.outputs = arrangement

    def row(self, outputs: List[str]) -> None:
        """Convenience method for single-row layout.

        This is equivalent to calling grid([outputs]).

        Args:
            outputs: List of output names to display in a single row

        Example:
            layout.row(["original", "filtered", "result"])

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        self.grid([outputs])

    # Aliases for backwards compatibility and alternative naming preferences
    set_style = style  # Alias: layout.set_style() is equivalent to layout.style()
    set_grid = grid  # Alias: layout.set_grid() is equivalent to layout.grid()
    canvas = grid  # Alias: layout.canvas() is equivalent to layout.grid()
    set_canvas = grid  # Alias: layout.set_canvas() is equivalent to layout.grid()


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
            audio.set("path/to/track.mp3")

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        setter = state.get("__set_audio")
        if setter:
            setter(audio_path)

    def play(self) -> None:
        """Start audio playback.

        Example:
            audio.play()

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        play_fn = state.get("__play")
        if play_fn:
            play_fn()

    def pause(self) -> None:
        """Pause audio playback.

        Example:
            audio.pause()

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        pause_fn = state.get("__pause")
        if pause_fn:
            pause_fn()

    def stop(self) -> None:
        """Stop audio playback.

        Example:
            audio.stop()

        Raises:
            RuntimeError: If called outside of filter execution context.
        """
        state = _get_framework_state()
        stop_fn = state.get("__stop")
        if stop_fn:
            stop_fn()


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
    """

    def __getitem__(self, key: str) -> Any:
        """Get item from context using dict-style access."""
        return get_context()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Set item in context using dict-style access."""
        get_context()[key] = value

    def __getattr__(self, name: str) -> Any:
        """Get item from context using attribute-style access."""
        try:
            return get_context()[name]
        except KeyError:
            raise AttributeError(
                f"Context has no attribute '{name}'. "
                f"Available keys: {list(get_context().keys())}"
            )

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
# SharedContext - Explicit sentinel for legacy code migration
# ============================================================================


class _InjectedSentinel:
    """Sentinel indicating this parameter will be auto-injected by the pipeline.

    This is a singleton - only one instance exists.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "SharedContext.injected()"


class SharedContext(dict):
    """Explicitly typed context for filter functions (legacy migration helper).

    Use `SharedContext.injected()` as the default value to indicate
    this parameter will be auto-injected by the pipeline. This makes
    the injection explicit and self-documenting, while maintaining
    backwards compatibility with existing code.

    Example:
        from interactive_pipe import SharedContext

        @interactive(brightness=(0.5, [0.0, 1.0]))
        def my_filter(img, brightness=0.5, global_params: SharedContext = SharedContext.injected()):
            global_params["__output_styles"]["result"] = {"title": f"B={brightness}"}
            return img

    Note:
        This is provided for legacy code migration. For new code, prefer using
        the `layout`, `context`, and `audio` module-level proxies instead:

        from interactive_pipe import layout, context

        @interactive(brightness=(0.5, [0.0, 1.0]))
        def my_filter(img, brightness=0.5):
            layout.style("result", title=f"B={brightness}")
            return img
    """

    _injected_sentinel = _InjectedSentinel()
    _deprecation_warned = False

    @classmethod
    def injected(cls) -> "_InjectedSentinel":
        """Marker indicating this context will be auto-injected by the pipeline.

        Returns:
            A sentinel object that signals the framework to inject the shared context.

        Example:
            def my_filter(img, global_params: SharedContext = SharedContext.injected()):
                ...
        """
        return cls._injected_sentinel

    @classmethod
    def _warn_deprecation_once(cls):
        """Emit a deprecation warning once per session."""
        if not cls._deprecation_warned:
            import warnings

            message = (
                "global_param or context parameter injection is deprecated. "
                "Consider migrating to the new API: use `layout.style()` for output styling, "
                "`layout.grid()` for output grid arrangement, "
                "`context` for shared state between filters, and `audio` for audio control. "
            )
            warnings.warn(
                message,
                DeprecationWarning,
                stacklevel=6,  # Adjust to point to user's filter function
            )
            cls._deprecation_warned = True

    @classmethod
    def _reset_warning(cls):
        """Reset the deprecation warning flag (for testing)."""
        cls._deprecation_warned = False


def is_injected_sentinel(value) -> bool:
    """Check if a value is the SharedContext.injected() sentinel.

    Args:
        value: The value to check

    Returns:
        True if the value is the injected sentinel, False otherwise.
    """
    return isinstance(value, _InjectedSentinel)


# ============================================================================
# Module-level instances (exported)
# ============================================================================

layout = _LayoutProxy()
audio = _AudioProxy()
context = _ContextProxy()  # Direct dict-like access to user context
