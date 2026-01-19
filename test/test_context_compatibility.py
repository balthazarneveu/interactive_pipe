"""Test compatibility between new context API and legacy global_params."""

import pytest
import numpy as np
from interactive_pipe import interactive, context, get_context, layout
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore


def test_new_api_and_legacy_coexist():
    """Test that new context API and legacy global_params can coexist."""

    @interactive()
    def legacy_filter(img, global_params={}):
        # Legacy API - still works
        if "__output_styles" not in global_params:
            global_params["__output_styles"] = {}
        global_params["__output_styles"]["legacy"] = {"title": "Legacy API"}

        # Can also use new context API in same filter
        context.legacy_data = "from_legacy_filter"
        return img

    @interactive()
    def new_api_filter(img):
        # New API - no global_params in signature
        layout.style("new", title="New API")
        context.new_data = "from_new_filter"

        # Can read data from legacy filter
        assert context.legacy_data == "from_legacy_filter"
        return img * 0.5

    @interactive()
    def mixed_filter(img, global_params={}):
        # Can use both in same filter
        if "__output_styles" not in global_params:
            global_params["__output_styles"] = {}
        global_params["__output_styles"]["mixed"] = {"title": "Mixed"}

        context.mixed_data = "from_mixed_filter"

        # Can read from both previous filters
        assert context.legacy_data == "from_legacy_filter"
        assert context.new_data == "from_new_filter"
        return img * 2

    img = np.ones((10, 10, 3))

    legacy_obj = FilterCore(apply_fn=legacy_filter, inputs=[0], outputs=["legacy"])
    new_obj = FilterCore(apply_fn=new_api_filter, inputs=["legacy"], outputs=["new"])
    mixed_obj = FilterCore(apply_fn=mixed_filter, inputs=["new"], outputs=["mixed"])

    pipeline = PipelineCore(
        filters=[legacy_obj, new_obj, mixed_obj],
        inputs=[0],
        outputs=[["mixed"]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # Verify both APIs worked
    assert pipeline.global_params["__output_styles"]["legacy"]["title"] == "Legacy API"
    assert pipeline.global_params["__output_styles"]["new"]["title"] == "New API"
    assert pipeline.global_params["__output_styles"]["mixed"]["title"] == "Mixed"

    # Verify context data
    assert pipeline._user_context["legacy_data"] == "from_legacy_filter"
    assert pipeline._user_context["new_data"] == "from_new_filter"
    assert pipeline._user_context["mixed_data"] == "from_mixed_filter"


def test_context_attribute_access_with_legacy():
    """Test that context attribute access works with legacy global_params."""

    @interactive()
    def filter_with_global_params(img, global_params={}):
        # Attribute-style access
        context.attr_data = "attribute"
        # Dict-style access
        context["dict_data"] = "dictionary"
        # get_context() style
        ctx = get_context()
        ctx["func_data"] = "function"

        # All should be accessible
        assert context.attr_data == "attribute"
        assert context["dict_data"] == "dictionary"
        assert ctx["func_data"] == "function"

        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=filter_with_global_params, inputs=[0], outputs=[0])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # All access methods should have stored data
    assert pipeline._user_context["attr_data"] == "attribute"
    assert pipeline._user_context["dict_data"] == "dictionary"
    assert pipeline._user_context["func_data"] == "function"


def test_legacy_global_params_separate_from_user_context():
    """Test that legacy global_params and user context are separate."""

    @interactive()
    def test_filter(img, global_params={}):
        # User context should not have internal keys
        global_params["__internal_key"] = "internal_value"
        context.user_key = "user_value"

        # Verify separation
        ctx = get_context()
        assert "user_key" in ctx
        assert "__internal_key" not in ctx  # Internal keys not in user context

        # But global_params has both user context AND internal keys
        assert global_params["__internal_key"] == "internal_value"

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

    # User context should only have user keys
    assert "user_key" in pipeline._user_context
    assert "__internal_key" not in pipeline._user_context

    # But global_params has internal keys
    assert "__internal_key" in pipeline.global_params


def test_all_context_aliases_with_legacy():
    """Test all context access methods work with legacy API."""

    @interactive()
    def comprehensive_filter(img, global_params={}):
        # Method 1: get_context()
        ctx = get_context()
        ctx["method1"] = "get_context"

        # Method 2: context dict-style
        context["method2"] = "dict_style"

        # Method 3: context attribute-style
        context.method3 = "attr_style"

        # All should be readable via all methods
        assert ctx["method2"] == "dict_style"
        assert ctx["method3"] == "attr_style"
        assert context["method1"] == "get_context"
        assert context.method1 == "get_context"
        assert context.method2 == "dict_style"
        assert context["method3"] == "attr_style"

        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=comprehensive_filter, inputs=[0], outputs=[0])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]
    pipeline.run()

    # All methods stored data correctly
    assert pipeline._user_context["method1"] == "get_context"
    assert pipeline._user_context["method2"] == "dict_style"
    assert pipeline._user_context["method3"] == "attr_style"


def test_shared_context_injected_sentinel():
    """Test that SharedContext.injected() returns a singleton sentinel."""
    from interactive_pipe import SharedContext

    sentinel1 = SharedContext.injected()
    sentinel2 = SharedContext.injected()

    # Same instance (singleton)
    assert sentinel1 is sentinel2
    assert repr(sentinel1) == "SharedContext.injected()"


def test_shared_context_is_injected_sentinel():
    """Test the is_injected_sentinel helper function."""
    from interactive_pipe.core.context import is_injected_sentinel, SharedContext

    sentinel = SharedContext.injected()

    assert is_injected_sentinel(sentinel) is True
    assert is_injected_sentinel({}) is False
    assert is_injected_sentinel(None) is False
    assert is_injected_sentinel("string") is False


def test_shared_context_explicit_injection_works():
    """Test that SharedContext.injected() works as a default value."""
    from interactive_pipe import SharedContext
    from interactive_pipe.core.context import SharedContext as SC

    # Reset warning flag for this test
    SC._reset_warning()

    @interactive()
    def filter_with_explicit_injection(
        img, global_params: SharedContext = SharedContext.injected()
    ):
        # Should work exactly like legacy global_params={}
        if "__output_styles" not in global_params:
            global_params["__output_styles"] = {}
        global_params["__output_styles"]["explicit"] = {"title": "Explicit Injection"}
        global_params["user_data"] = "test_value"
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(
        apply_fn=filter_with_explicit_injection, inputs=[0], outputs=[0]
    )

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]

    # Should emit deprecation warning
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        # Check that deprecation warning was emitted
        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert "deprecated" in str(deprecation_warnings[0].message).lower()
        assert "layout" in str(deprecation_warnings[0].message).lower()

    # Verify the filter worked correctly
    assert "user_data" in pipeline.global_params
    assert pipeline.global_params["user_data"] == "test_value"
    assert (
        pipeline.global_params["__output_styles"]["explicit"]["title"]
        == "Explicit Injection"
    )


def test_shared_context_warning_only_once():
    """Test that deprecation warning is only emitted once per session."""
    from interactive_pipe import SharedContext
    from interactive_pipe.core.context import SharedContext as SC

    # Reset warning flag for this test
    SC._reset_warning()

    @interactive()
    def filter1(img, global_params: SharedContext = SharedContext.injected()):
        return img

    @interactive()
    def filter2(img, global_params: SharedContext = SharedContext.injected()):
        return img

    img = np.ones((10, 10, 3))
    filter_obj1 = FilterCore(apply_fn=filter1, inputs=[0], outputs=["out1"])
    filter_obj2 = FilterCore(apply_fn=filter2, inputs=["out1"], outputs=["out2"])

    pipeline = PipelineCore(
        filters=[filter_obj1, filter_obj2],
        inputs=[0],
        outputs=[["out2"]],
        cache=False,
    )
    pipeline.inputs = [img]

    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        # Should only warn once, even though two filters use SharedContext.injected()
        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 1


def test_shared_context_keeps_variable_name():
    """Test that users can keep any variable name with SharedContext.injected()."""
    from interactive_pipe import SharedContext
    from interactive_pipe.core.context import SharedContext as SC

    # Reset warning flag for this test
    SC._reset_warning()

    @interactive()
    def filter_with_context_name(
        img, context: SharedContext = SharedContext.injected()
    ):
        # Using 'context' as variable name (one of EQUIVALENT_STATE_KEYS)
        context["my_data"] = "test"
        return img

    @interactive()
    def filter_with_state_name(img, state: SharedContext = SharedContext.injected()):
        # Using 'state' as variable name (another EQUIVALENT_STATE_KEYS)
        state["other_data"] = "test2"
        return img

    img = np.ones((10, 10, 3))

    # Test with 'context' name
    SC._reset_warning()
    filter_obj = FilterCore(apply_fn=filter_with_context_name, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]

    import warnings

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        pipeline.run()

    assert pipeline.global_params["my_data"] == "test"

    # Test with 'state' name
    SC._reset_warning()
    filter_obj2 = FilterCore(apply_fn=filter_with_state_name, inputs=[0], outputs=[0])
    pipeline2 = PipelineCore(
        filters=[filter_obj2],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline2.inputs = [img]

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        pipeline2.run()

    assert pipeline2.global_params["other_data"] == "test2"


def test_legacy_empty_dict_shows_warning():
    """Test that legacy global_params={} DOES emit deprecation warning."""
    from interactive_pipe.core.context import SharedContext as SC

    # Reset warning flag for this test
    SC._reset_warning()

    @interactive()
    def legacy_filter(img, global_params={}):
        global_params["legacy_key"] = "legacy_value"
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=legacy_filter, inputs=[0], outputs=[0])

    pipeline = PipelineCore(
        filters=[filter_obj],
        inputs=[0],
        outputs=[[0]],
        cache=False,
    )
    pipeline.inputs = [img]

    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        # Should emit SharedContext deprecation warning
        shared_context_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DeprecationWarning)
            and "deprecated" in str(warning.message).lower()
        ]
        assert len(shared_context_warnings) >= 1

    # Filter should still work
    assert pipeline.global_params["legacy_key"] == "legacy_value"


def test_shared_context_import_from_package():
    """Test that SharedContext can be imported from interactive_pipe."""
    from interactive_pipe import SharedContext

    assert hasattr(SharedContext, "injected")
    assert callable(SharedContext.injected)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
