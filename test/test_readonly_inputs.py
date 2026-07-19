"""Tests for read-only filter inputs (readonly_inputs=True by default).

Filters receive their numpy inputs as read-only views: in-place mutation raises a
ValueError at the offending line instead of silently corrupting sibling filters
(same-run aliasing) or cached buffers (compounding corruption under cache=True).
Filters declaring inplace=True receive private writable deep copies instead.
"""

import numpy as np
import pytest

from interactive_pipe.core.engine import FilterError
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore
from interactive_pipe.helper.filter_decorator import interactive
from interactive_pipe.helper.pipeline_decorator import interactive_pipeline

input_image = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def mutating_add(img, p=5.0):
    img += p  # in-place mutation of the input
    return [img]


def clean_add(img, p=5.0):
    return [img + p]


def test_readonly_inputs_blocks_inplace_mutation():
    filt = FilterCore(apply_fn=mutating_add, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1])
    pip.inputs = [input_image]

    with pytest.raises(FilterError) as exc_info:
        pip.run()
    assert isinstance(exc_info.value.original_error, ValueError)


def test_readonly_inputs_opt_out_restores_legacy_behavior():
    filt = FilterCore(apply_fn=mutating_add, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1], readonly_inputs=False)
    pip.inputs = [input_image]

    res = pip.run()
    assert np.allclose(res[1], input_image + 5.0)


def test_inplace_filter_gets_private_writable_copy():
    filt = FilterCore(apply_fn=mutating_add, inputs=[0], outputs=[1], inplace=True)
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1])
    pip.inputs = [input_image]

    res = pip.run()
    assert np.allclose(res[1], input_image + 5.0)
    # the original input is untouched (the filter mutated a private copy)
    assert np.allclose(input_image, np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))


def test_inplace_filter_does_not_corrupt_cache():
    """The compounding-corruption scenario: with cache=True, an in-place filter used to
    mutate the upstream filter's cached buffer when served by reference (wrong results
    from the 3rd run on). inplace=True must keep every run exact."""
    counters = {"first": 0}

    def first(img, gain=1.0):
        counters["first"] += 1
        return [img * gain]

    filt1 = FilterCore(apply_fn=first, inputs=[0], outputs=[1])
    filt2 = FilterCore(apply_fn=mutating_add, inputs=[1], outputs=[2], inplace=True)
    pip = PipelineCore(filters=[filt1, filt2], inputs=[0], outputs=[2], cache=True)
    pip.inputs = [input_image]

    res = pip.run()
    assert np.allclose(res[2], input_image + 5.0)

    # run 2: 'first' is served from cache, the in-place filter must not corrupt it
    pip.parameters = {"mutating_add": {"p": 3.0}}
    res = pip.run()
    assert counters == {"first": 1}
    assert np.allclose(res[2], input_image + 3.0)

    # run 3: the historical bug showed up here (cached buffer previously mutated)
    pip.parameters = {"mutating_add": {"p": 4.0}}
    res = pip.run()
    assert counters == {"first": 1}
    assert np.allclose(res[2], input_image + 4.0)


def test_readonly_inputs_protects_sibling_aliasing():
    """Two filters consuming the same buffer: the first one mutating it must raise
    instead of silently feeding the second one a modified image."""
    filt_a = FilterCore(apply_fn=mutating_add, inputs=[0], outputs=[1])
    filt_b = FilterCore(apply_fn=clean_add, inputs=[0], outputs=[2])
    pip = PipelineCore(filters=[filt_a, filt_b], inputs=[0], outputs=[1, 2])
    pip.inputs = [input_image]

    with pytest.raises(FilterError):
        pip.run()


def test_readonly_inputs_wraps_list_of_images():
    """Buffers nested in list inputs (e.g. img_list pipelines) are protected too."""

    def select_and_mutate(img_list, index=0):
        img = img_list[0]
        img *= 2.0  # element of the list input is read-only
        return [img]

    filt = FilterCore(apply_fn=select_and_mutate, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1])
    pip.inputs = [[input_image, input_image]]

    with pytest.raises(FilterError):
        pip.run()


# pipeline functions must live at module level: the AST parser reads their source
@interactive(inplace=True, p=(5.0, [0.0, 10.0]))
def legacy_style(img, p=5.0):
    img += p
    return img


@interactive()
def passthrough(img):
    return img


@interactive()
def bad_mutator(img):
    img += 1.0
    return img


def inplace_pipe(img):
    y = legacy_style(img)
    z = passthrough(y)
    return [z]


def bad_pipe(img):
    y = bad_mutator(img)
    return [y]


def test_interactive_decorator_inplace_passthrough():
    """@interactive(inplace=True) flows through interactive_pipeline to the FilterCore."""
    headless = interactive_pipeline(gui=None, cache=True)(inplace_pipe)
    res = headless(input_image)
    assert np.allclose(res[0], input_image + 5.0)


def test_interactive_decorator_default_blocks_mutation():
    headless = interactive_pipeline(gui=None)(bad_pipe)
    with pytest.raises(FilterError):
        headless(input_image)


def test_readonly_inputs_with_graph_cache():
    """Protection composes with the dependency-aware cache: cache hits serve buffers
    that stay safe from downstream mutation."""
    filt1 = FilterCore(apply_fn=clean_add, name="first", inputs=[0], outputs=[1])
    filt2 = FilterCore(apply_fn=mutating_add, inputs=[1], outputs=[2], inplace=True)
    pip = PipelineCore(filters=[filt1, filt2], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    res = pip.run()
    assert np.allclose(res[2], input_image + 10.0)
    pip.parameters = {"mutating_add": {"p": 1.0}}
    res = pip.run()
    assert np.allclose(res[2], input_image + 6.0)


class _FakeTensor:
    """Mimics the duck-typed torch surface the engine relies on: type(x).__module__
    rooted at "torch" and an autograd version counter bumped by in-place ops."""

    __module__ = "torch"

    def __init__(self, value=0.0):
        self.value = value
        self._version = 0

    def mul_(self, factor):  # in-place op, like torch
        self.value *= factor
        self._version += 1
        return self


def test_torch_tensor_inplace_mutation_detected():
    """Torch tensors cannot be made read-only: mutation is detected right after the
    filter runs through the version counter, on the very first run."""

    def bad(tensor, gain=2.0):
        tensor.mul_(gain)
        return [tensor]

    filt = FilterCore(apply_fn=bad, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1])
    pip.inputs = [_FakeTensor(3.0)]

    with pytest.raises(FilterError) as exc_info:
        pip.run()
    assert isinstance(exc_info.value.original_error, RuntimeError)
    assert "in-place mutation of a torch tensor" in str(exc_info.value.original_error)


def test_torch_tensor_inplace_filter_allowed():
    """inplace=True filters receive deep copies: tensor mutation is safe and permitted."""

    def legacy(tensor, gain=2.0):
        tensor.mul_(gain)
        return [tensor]

    original = _FakeTensor(3.0)
    filt = FilterCore(apply_fn=legacy, inputs=[0], outputs=[1], inplace=True)
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1], safe_input_buffer_deepcopy=False)
    pip.inputs = [original]

    res = pip.run()
    assert res[1].value == 6.0
    assert original.value == 3.0  # the filter mutated a private copy


def test_torch_tensor_nested_in_list_detected():
    def bad(tensor_list):
        tensor_list[0].mul_(2.0)
        return [tensor_list[0]]

    filt = FilterCore(apply_fn=bad, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1])
    pip.inputs = [[_FakeTensor(1.0)]]

    with pytest.raises(FilterError):
        pip.run()


def test_torch_real_tensor_mutation_detected():
    """Same contract against real torch, when available."""
    torch = pytest.importorskip("torch")

    def bad(tensor, gain=2.0):
        tensor += gain  # in-place on torch tensors
        return [tensor]

    filt = FilterCore(apply_fn=bad, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt], inputs=[0], outputs=[1])
    pip.inputs = [torch.zeros(2, 3)]

    with pytest.raises(FilterError):
        pip.run()
