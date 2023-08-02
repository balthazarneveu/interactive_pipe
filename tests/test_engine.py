import numpy as np
import pytest
from copy import deepcopy

try:
    from interactive_pipe.core import FilterCore, PipelineEngine
except:
    import helper
    from core import FilterCore, PipelineEngine

input_image = np.array([[1, 2, 3], [4, 5, 6]])


def mad(img, coeff=2, bias=-3):
    mad_res = img*coeff+bias
    return [mad_res]


def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]

# NOTE: tests both FilterCore & PipelineEngine


@pytest.mark.parametrize("cache", [True, False])
def test_engine(cache):
    # Define two filters:
    # - first filter  =  mad (multiply and add)
    # - second filter =  blending between 2 images
    # Default parameters are used.
    filt1 = FilterCore(apply_fn=mad, outputs=[2])
    filt2 = FilterCore(apply_fn=blend, inputs=[0, 2], outputs=[8])
    cache = True
    pip = PipelineEngine(cache=cache, safe_input_buffer_deepcopy=True)
    expected_filt1 = (2*input_image - 3)
    # 1/ execute for the first time
    res = pip.run([filt1, filt2], imglst=[input_image])
    if cache:
        assert filt1.cache_mem.state_change.update_needed
        assert filt2.cache_mem.state_change.update_needed

    assert (res[2] == expected_filt1).all()
    assert (res[8] == 0.4*input_image+0.6*expected_filt1).all()

    # 2/ do it again
    # cache shall be used for the two filters as no parameters were updated
    res = pip.run([filt1, filt2], imglst=[input_image])
    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert not filt2.cache_mem.state_change.update_needed

    # 3/ change parameters of the second filter and go again
    # first filter shall use its cache, second filter needs reprocessing
    filt2.values["blend_coeff"] = 0.8
    res = pip.run([filt1, filt2], imglst=[input_image])
    assert np.allclose(res[8], (0.8*input_image+0.2*expected_filt1))

    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert filt2.cache_mem.state_change.update_needed

    # 4/ do it once more, nothing has changed, cache is reused
    res = pip.run([filt1, filt2], imglst=[input_image])
    assert np.allclose(res[8], (0.8*input_image+0.2*expected_filt1))
    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert not filt2.cache_mem.state_change.update_needed
