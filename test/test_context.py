"""Tests for the clean context API (layout, audio, get_context)."""

import pytest
import numpy as np
from interactive_pipe import (
    interactive,
    get_context,
    layout,
    audio,
)
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore


def test_get_context_outside_pipeline_raises_error():
    """Test that get_context() raises error when called outside pipeline."""
    with pytest.raises(RuntimeError, match="outside of pipeline execution"):
        get_context()


def test_layout_style_outside_pipeline_raises_error():
    """Test that layout.style() raises error when called outside pipeline."""
    with pytest.raises(RuntimeError, match="outside of filter execution"):
        layout.style("test", title="Test")


def test_layout_grid_outside_pipeline_raises_error():
    """Test that layout.grid() raises error when called outside pipeline."""
    with pytest.raises(RuntimeError, match="outside of filter execution"):
        layout.grid([["test"]])


def test_audio_operations_outside_pipeline_do_not_crash():
    """Test that audio operations don't crash when called outside pipeline."""
    # These should fail silently or raise RuntimeError
    with pytest.raises(RuntimeError, match="outside of filter execution"):
        audio.set("test.mp3")
    with pytest.raises(RuntimeError, match="outside of filter execution"):
        audio.play()


def test_get_context_returns_user_dict():
    """Test that get_context() returns the user context dictionary."""

    @interactive()
    def test_filter(img, global_params={}):
        ctx = get_context()
        ctx["test_key"] = "test_value"
        ctx["number"] = 42
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=test_filter, inputs=[0], outputs=[0])

    # Create a minimal pipeline
    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]

    # Run the pipeline
    pipeline.run()

    # Check that user context was populated
    assert "test_key" in pipeline._user_context
    assert pipeline._user_context["test_key"] == "test_value"
    assert pipeline._user_context["number"] == 42


def test_get_context_no_internal_keys_visible():
    """Test that get_context() does not expose internal __keys."""

    @interactive()
    def test_filter(img, global_params={}):
        ctx = get_context()
        # User context should not have __pipeline, __output_styles, etc.
        assert "__pipeline" not in ctx
        assert "__output_styles" not in ctx
        assert "__set_audio" not in ctx
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=test_filter, inputs=[0], outputs=[0])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()


def test_layout_style_sets_title():
    """Test that layout.style() correctly sets output title."""

    @interactive(brightness=(0.5, [0.0, 1.0]))
    def adjust_brightness(img, brightness=0.5, global_params={}):
        layout.style("adjusted", title=f"Brightness: {brightness:.2f}")
        return img * brightness

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(
        apply_fn=adjust_brightness, inputs=[0], outputs=["adjusted"]
    )

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["adjusted"]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # Check that __output_styles was set correctly
    assert "__output_styles" in pipeline.global_params
    assert "adjusted" in pipeline.global_params["__output_styles"]
    assert (
        pipeline.global_params["__output_styles"]["adjusted"]["title"]
        == "Brightness: 0.50"
    )


def test_layout_style_with_extra_style_kwargs():
    """Test that layout.style() supports additional style kwargs."""

    @interactive()
    def test_filter(img, global_params={}):
        layout.style(
            "output",
            title="Test",
            colormap="viridis",
            vmin=0,
            vmax=1,
        )
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=test_filter, inputs=[0], outputs=["output"])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["output"]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    style = pipeline.global_params["__output_styles"]["output"]
    assert style["title"] == "Test"
    assert style["colormap"] == "viridis"
    assert style["vmin"] == 0
    assert style["vmax"] == 1


def test_layout_grid_sets_pipeline_outputs():
    """Test that layout.grid() correctly sets pipeline.outputs."""

    @interactive()
    def test_filter(img, global_params={}):
        layout.grid([["img1", "img2"], ["img3", "img4"]])
        # Store result in global_params to verify it was set
        global_params["layout_was_set"] = True
        return img, img * 0.5, img * 0.25, img * 0.1

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(
        apply_fn=test_filter,
        inputs=[0],
        outputs=["img1", "img2", "img3", "img4"],
    )

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["img1"]],  # Initial value
        cache=False,
    )
    # Need to set __pipeline so layout.grid can access it
    pipeline.global_params["__pipeline"] = pipeline
    pipeline.inputs = [img]
    pipeline.run()

    # Check that pipeline.outputs was updated
    assert pipeline.outputs == [["img1", "img2"], ["img3", "img4"]]
    assert pipeline.global_params.get("layout_was_set") is True


def test_layout_row_sets_single_row_layout():
    """Test that layout.row() creates a single-row layout."""

    @interactive()
    def test_filter(img, global_params={}):
        layout.row(["img1", "img2", "img3"])
        return img, img * 0.5, img * 0.25

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(
        apply_fn=test_filter,
        inputs=[0],
        outputs=["img1", "img2", "img3"],
    )

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["img1"]],
        cache=False,
    )
    # Need to set __pipeline so layout.row can access it
    pipeline.global_params["__pipeline"] = pipeline
    pipeline.inputs = [img]
    pipeline.run()

    # Check that pipeline.outputs is a single row
    assert pipeline.outputs == [["img1", "img2", "img3"]]


def test_context_shared_between_filters():
    """Test that get_context() allows sharing data between filters."""

    @interactive()
    def filter_a(img, global_params={}):
        ctx = get_context()
        ctx["from_a"] = "data from filter A"
        ctx["count"] = 42
        return img

    @interactive()
    def filter_b(img, global_params={}):
        ctx = get_context()
        # Should be able to read data from filter A
        assert ctx.get("from_a") == "data from filter A"
        assert ctx.get("count") == 42
        ctx["from_b"] = "data from filter B"
        return img * 2

    img = np.ones((10, 10, 3))
    filter_a_obj = FilterCore(apply_fn=filter_a, inputs=[0], outputs=["img_a"])
    filter_b_obj = FilterCore(apply_fn=filter_b, inputs=["img_a"], outputs=["img_b"])

    pipeline = PipelineCore(
        filters=[filter_a_obj, filter_b_obj],
        inputs=[0],
        outputs=[["img_b"]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # Check that user context has data from both filters
    assert pipeline._user_context["from_a"] == "data from filter A"
    assert pipeline._user_context["from_b"] == "data from filter B"
    assert pipeline._user_context["count"] == 42


def test_legacy_global_params_still_works():
    """Test that the legacy global_params signature still works."""

    @interactive()
    def legacy_filter(img, global_params={}):
        # Initialize __output_styles if not present (normally done by GUI)
        if "__output_styles" not in global_params:
            global_params["__output_styles"] = {}
        # Legacy approach should still work
        global_params["__output_styles"]["output"] = {"title": "Legacy"}
        # But new API should also work
        ctx = get_context()
        ctx["legacy_test"] = True
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=legacy_filter, inputs=[0], outputs=["output"])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["output"]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # Both legacy and new API should work
    assert pipeline.global_params["__output_styles"]["output"]["title"] == "Legacy"
    assert pipeline._user_context["legacy_test"] is True


def test_new_api_without_global_params_signature():
    """Test that new API works without global_params in function signature."""
    # Need to clear registered_controls_names to avoid conflicts
    from interactive_pipe.helper import _private

    _private.registered_controls_names = []

    @interactive(
        gain=(0.5, [0.0, 1.0])
    )  # Using 'gain' instead of 'brightness' to avoid conflicts
    def clean_filter(img, gain=0.5):
        # No global_params in signature - clean!
        layout.style("result", title=f"G={gain:.2f}")
        ctx = get_context()
        ctx["gain_used"] = gain
        return img * gain

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=clean_filter, inputs=[0], outputs=["result"])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["result"]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # Check that everything works without global_params signature
    assert pipeline.global_params["__output_styles"]["result"]["title"] == "G=0.50"
    assert pipeline._user_context["gain_used"] == 0.5


def test_audio_proxy_delegates_correctly():
    """Test that audio proxy delegates to framework callbacks."""

    audio_operations = []

    @interactive()
    def test_audio_filter(img, global_params={}):
        # Mock audio callbacks
        global_params["__set_audio"] = lambda path: audio_operations.append(
            ("set", path)
        )
        global_params["__play"] = lambda: audio_operations.append(("play",))
        global_params["__pause"] = lambda: audio_operations.append(("pause",))
        global_params["__stop"] = lambda: audio_operations.append(("stop",))

        # Use audio API
        audio.set("test.mp3")
        audio.play()
        audio.pause()
        audio.stop()

        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=test_audio_filter, inputs=[0], outputs=[0])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # Check that audio operations were called
    assert ("set", "test.mp3") in audio_operations
    assert ("play",) in audio_operations
    assert ("pause",) in audio_operations
    assert ("stop",) in audio_operations


def test_context_isolation_between_pipeline_runs():
    """Test that user context is isolated between different pipeline runs."""

    @interactive()
    def counter_filter(img, global_params={}):
        ctx = get_context()
        count = ctx.get("count", 0)
        ctx["count"] = count + 1
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=counter_filter, inputs=[0], outputs=[0])

    # First pipeline run
    pipeline1 = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline1.inputs = [img]
    pipeline1.run()
    assert pipeline1._user_context["count"] == 1

    # Second pipeline run (different pipeline instance)
    pipeline2 = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline2.inputs = [img]
    pipeline2.run()
    # Should start fresh, not continue from pipeline1
    assert pipeline2._user_context["count"] == 1


def test_layout_aliases():
    """Test that layout aliases work (set_style, set_grid, canvas, set_canvas)."""

    @interactive()
    def test_filter(img, global_params={}):
        # Test set_style alias
        layout.set_style("output1", title="Using set_style alias")
        # Test set_grid alias
        layout.set_grid([["output1", "output2"]])
        return img, img * 0.5

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(
        apply_fn=test_filter, inputs=[0], outputs=["output1", "output2"]
    )

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[["output1"]],
        cache=False,
    )
    pipeline.global_params["__pipeline"] = pipeline
    pipeline.inputs = [img]
    pipeline.run()

    # Check that set_style alias works
    assert pipeline.global_params["__output_styles"]["output1"]["title"] == (
        "Using set_style alias"
    )
    # Check that set_grid alias works
    assert pipeline.outputs == [["output1", "output2"]]


def test_layout_canvas_aliases():
    """Test that layout.canvas and layout.set_canvas aliases work."""

    @interactive()
    def test_canvas_filter(img, global_params={}):
        # Test canvas alias
        layout.canvas([["a", "b"], ["c", "d"]])
        return img, img * 0.5, img * 0.25, img * 0.1

    @interactive()
    def test_set_canvas_filter(img, global_params={}):
        # Test set_canvas alias
        layout.set_canvas([["x", "y"]])
        return img, img * 2

    img = np.ones((10, 10, 3))

    # Test canvas alias
    filter1 = FilterCore(
        apply_fn=test_canvas_filter, inputs=[0], outputs=["a", "b", "c", "d"]
    )
    pipeline1 = PipelineCore(
        filters=[filter1], inputs=[0], outputs=[["a"]], cache=False
    )
    pipeline1.global_params["__pipeline"] = pipeline1
    pipeline1.inputs = [img]
    pipeline1.run()
    assert pipeline1.outputs == [["a", "b"], ["c", "d"]]

    # Test set_canvas alias
    filter2 = FilterCore(
        apply_fn=test_set_canvas_filter, inputs=[0], outputs=["x", "y"]
    )
    pipeline2 = PipelineCore(
        filters=[filter2], inputs=[0], outputs=[["x"]], cache=False
    )
    pipeline2.global_params["__pipeline"] = pipeline2
    pipeline2.inputs = [img]
    pipeline2.run()
    assert pipeline2.outputs == [["x", "y"]]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
