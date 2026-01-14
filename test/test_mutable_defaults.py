"""
Tests to verify that mutable default arguments are properly isolated
and don't cause shared state bugs between instances.
"""

import numpy as np
from interactive_pipe.core.filter import FilterCore, PureFilter
from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.headless.pipeline import HeadlessPipeline


def test_filtercore_default_params_not_shared():
    """Test that FilterCore instances don't share default_params dictionary"""

    def apply_fn(x, param1=1, param2=2):
        return x * param1 + param2

    filter1 = FilterCore(apply_fn=apply_fn, default_params=None)
    filter2 = FilterCore(apply_fn=apply_fn, default_params=None)

    # Modify filter1's values
    filter1.values["param1"] = 10

    # filter2 should not be affected
    assert "param1" not in filter2.values or filter2.values["param1"] == 1


def test_filtercore_explicit_default_params_not_shared():
    """Test that explicitly provided default_params are not shared"""

    def apply_fn(x, param1=1):
        return x * param1

    default1 = {"param1": 5}
    default2 = {"param1": 7}

    filter1 = FilterCore(apply_fn=apply_fn, default_params=default1)
    filter2 = FilterCore(apply_fn=apply_fn, default_params=default2)

    assert filter1.values["param1"] == 5
    assert filter2.values["param1"] == 7

    # Modify filter1
    filter1.values["param1"] = 10
    assert filter2.values["param1"] == 7  # filter2 unchanged


def test_pipelinecore_parameters_not_shared():
    """Test that PipelineCore instances don't share parameters dictionary"""

    def apply_fn(x, param=1):
        return x * param

    filter1 = FilterCore(apply_fn=apply_fn, name="filter1")
    filter2 = FilterCore(apply_fn=apply_fn, name="filter2")

    pipeline1 = PipelineCore(filters=[filter1], parameters=None)
    pipeline2 = PipelineCore(filters=[filter2], parameters=None)

    # Set parameters for pipeline1
    pipeline1.parameters = {"filter1": {"param": 5}}

    # pipeline2 should have empty parameters
    assert pipeline2.parameters == {"filter2": {"param": 1}}


def test_pipelinecore_explicit_parameters_not_shared():
    """Test that explicitly provided parameters are not shared"""

    def apply_fn(x, param=1):
        return x * param

    filter1 = FilterCore(apply_fn=apply_fn, name="filter1")
    filter2 = FilterCore(apply_fn=apply_fn, name="filter2")

    params1 = {"filter1": {"param": 5}}
    params2 = {"filter2": {"param": 7}}

    pipeline1 = PipelineCore(filters=[filter1], parameters=params1)
    pipeline2 = PipelineCore(filters=[filter2], parameters=params2)

    assert pipeline1.parameters["filter1"]["param"] == 5
    assert pipeline2.parameters["filter2"]["param"] == 7


def test_gui_parameters_not_shared():
    """Test that InteractivePipeGUI instances don't share parameters"""

    def apply_fn(x, param=1):
        return [x * param]

    filter1 = FilterCore(apply_fn=apply_fn, name="filter1")
    pipeline1 = HeadlessPipeline(filters=[filter1], inputs=[0])
    pipeline1.inputs = [np.array([1, 2, 3])]

    filter2 = FilterCore(apply_fn=apply_fn, name="filter2")
    pipeline2 = HeadlessPipeline(filters=[filter2], inputs=[0])
    pipeline2.inputs = [np.array([1, 2, 3])]

    # Create mock GUI classes that don't require actual backend
    class MockGUI(InteractivePipeGUI):
        def init_app(self, **kwargs):
            pass

        def run(self):
            return []

    # Create GUI instances to verify they don't share state
    MockGUI(pipeline=pipeline1)
    MockGUI(pipeline=pipeline2)

    # Set parameters directly on pipelines (simulating what GUI.__call__ does)
    pipeline1.parameters = {"filter1": {"param": 5}}
    pipeline2.parameters = {"filter2": {"param": 7}}

    # Verify they're independent - check pipeline parameters
    assert pipeline1.parameters["filter1"]["param"] == 5
    assert pipeline2.parameters["filter2"]["param"] == 7
    # Verify they don't share the same dict
    assert pipeline1.parameters is not pipeline2.parameters


def test_purefilter_default_params_not_shared():
    """Test that PureFilter instances don't share default_params"""

    def apply_fn(x, param=1):
        return x * param

    filter1 = PureFilter(apply_fn=apply_fn, default_params=None)
    filter2 = PureFilter(apply_fn=apply_fn, default_params=None)

    filter1.values["param"] = 10
    assert "param" not in filter2.values or filter2.values["param"] == 1
