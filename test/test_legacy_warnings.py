"""Test that all legacy parameter injection patterns show deprecation warnings."""

import pytest
import numpy as np
import warnings
from interactive_pipe import interactive
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.core.context import SharedContext as SC


def test_global_params_empty_dict_warns():
    """Test that global_params={} shows deprecation warning."""
    SC._reset_warning()

    @interactive()
    def my_filter(img, global_params={}):
        global_params["test"] = "value"
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=my_filter, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj], inputs=[0], outputs=[[0]], cache=False
    )
    pipeline.inputs = [img]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert "deprecated" in str(deprecation_warnings[0].message).lower()


def test_global_params_none_warns():
    """Test that global_params=None shows deprecation warning."""
    SC._reset_warning()

    @interactive()
    def my_filter(img, global_params=None):
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=my_filter, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj], inputs=[0], outputs=[[0]], cache=False
    )
    pipeline.inputs = [img]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1


def test_context_parameter_warns():
    """Test that context={} shows deprecation warning."""
    SC._reset_warning()

    @interactive()
    def my_filter(img, context={}):
        context["test"] = "value"
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=my_filter, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj], inputs=[0], outputs=[[0]], cache=False
    )
    pipeline.inputs = [img]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1


def test_state_parameter_warns():
    """Test that state={} shows deprecation warning."""
    SC._reset_warning()

    @interactive()
    def my_filter(img, state={}):
        state["test"] = "value"
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=my_filter, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj], inputs=[0], outputs=[[0]], cache=False
    )
    pipeline.inputs = [img]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1


def test_shared_context_injected_warns():
    """Test that SharedContext.injected() shows deprecation warning."""
    SC._reset_warning()

    from interactive_pipe import SharedContext

    @interactive()
    def my_filter(img, global_params: SharedContext = SharedContext.injected()):
        if "__output_styles" not in global_params:
            global_params["__output_styles"] = {}
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=my_filter, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj], inputs=[0], outputs=[[0]], cache=False
    )
    pipeline.inputs = [img]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1


def test_warning_message_content():
    """Test that warning message mentions the new API."""
    SC._reset_warning()

    @interactive()
    def my_filter(img, global_params={}):
        return img

    img = np.ones((10, 10, 3))
    filter_obj = FilterCore(apply_fn=my_filter, inputs=[0], outputs=[0])
    pipeline = PipelineCore(
        filters=[filter_obj], inputs=[0], outputs=[[0]], cache=False
    )
    pipeline.inputs = [img]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipeline.run()

        deprecation_warnings = [
            warning for warning in w if issubclass(warning.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1

        message = str(deprecation_warnings[0].message)
        # Should mention new API components
        assert "layout" in message.lower() or "context" in message.lower()
        assert "deprecated" in message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
