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
            layout.output("analysis", title=f"Found {count} objects")
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
# Module-level instances (exported)
# ============================================================================

layout = _LayoutProxy()
audio = _AudioProxy()
