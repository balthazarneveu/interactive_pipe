"""Tests for the fail-loudly behavior of the APIs removed in 0.9.0.

The legacy dict-injection pattern (declaring global_params={} or similar in a
filter signature) and the pipeline-init aliases of context= were removed.
They must fail with a clear TypeError instead of silently misbehaving.
"""

import numpy as np
import pytest

import interactive_pipe
from interactive_pipe import interactive_pipeline
from interactive_pipe.core.context import REMOVED_CONTEXT_ALIASES, REMOVED_CONTEXT_KWARGS
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore


def simple_filter(img, coeff=2):
    return img * coeff


@pytest.mark.parametrize("magic_kwarg", REMOVED_CONTEXT_KWARGS)
def test_filter_with_magic_kwarg_raises_typeerror(magic_kwarg):
    """Declaring a removed magic kwarg in a filter signature fails at construction."""
    namespace = {}
    exec(
        f"def legacy_filter(img, {magic_kwarg}={{}}, coeff=2):\n    return img * coeff",
        namespace,
    )
    with pytest.raises(TypeError, match="removed in interactive_pipe 0.9.0"):
        FilterCore(apply_fn=namespace["legacy_filter"], inputs=[0], outputs=[0])


def test_magic_kwarg_error_mentions_the_replacement():
    def legacy_filter(img, global_params={}):
        return img

    with pytest.raises(TypeError, match="context") as excinfo:
        FilterCore(apply_fn=legacy_filter, inputs=[0], outputs=[0])
    assert "layout" in str(excinfo.value)
    assert "global_params" in str(excinfo.value)


@pytest.mark.parametrize("alias", REMOVED_CONTEXT_ALIASES)
def test_pipeline_init_alias_raises_typeerror(alias):
    """Passing a removed context alias at pipeline init fails with a clear message."""
    filt = FilterCore(apply_fn=simple_filter, inputs=[0], outputs=[1])
    with pytest.raises(TypeError, match="removed in interactive_pipe 0.9.0"):
        PipelineCore(filters=[filt], inputs=[0], outputs=[[1]], **{alias: {"ratio": 5}})


@pytest.mark.parametrize("alias", REMOVED_CONTEXT_ALIASES)
def test_interactive_pipeline_decorator_alias_raises_typeerror(alias):
    with pytest.raises(TypeError, match="removed in interactive_pipe 0.9.0"):
        interactive_pipeline(gui=None, **{alias: {"ratio": 5}})


def test_pipeline_init_context_still_works():
    """The modern context= argument is unaffected by the removal."""
    filt = FilterCore(apply_fn=simple_filter, inputs=[0], outputs=[1])
    pipeline = PipelineCore(filters=[filt], inputs=[0], outputs=[[1]], context={"ratio": 5}, cache=False)
    pipeline.inputs = [np.ones((4, 4, 3))]
    pipeline.run()
    assert pipeline.global_params["ratio"] == 5
    assert pipeline._user_context["ratio"] == 5


def test_shared_context_export_removed():
    assert not hasattr(interactive_pipe, "SharedContext")


def test_ordinary_kwargs_are_unaffected():
    """Regular keyword arguments that are not magic names still work normally."""

    def normal_filter(img, gain=0.5, ctx_label="none"):
        return img * gain

    filt = FilterCore(apply_fn=normal_filter, inputs=[0], outputs=[1])
    assert filt.values == {"gain": 0.5, "ctx_label": "none"}
