import numpy as np
import pytest
from copy import deepcopy

try:
    from interactive_pipe.core.filter import FilterCore
    from interactive_pipe.core.engine import PipelineEngine
    from interactive_pipe.core.pipeline import PipelineCore
except:
    import helper
    from core.filter import FilterCore
    from core.engine import PipelineEngine
    from core.pipeline import PipelineCore

input_image = np.array([[1, 2, 3], [4, 5, 6]])


def mad(img, coeff=2, bias=-3):
    mad_res = img*coeff+bias
    return [mad_res]


def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]

# NOTE: tests both FilterCore & PipelineEngine & PipelineCore


@pytest.mark.parametrize("cache", [True, False])
@pytest.mark.parametrize("engine_flag", [True, False])
def test_engine(cache, engine_flag):
    # Define two filters:
    # - first filter  =  mad (multiply and add)
    # - second filter =  blending between 2 images
    # Default parameters are used.
    filt1 = FilterCore(apply_fn=mad, outputs=[2])
    filt2 = FilterCore(apply_fn=blend, inputs=[0, 2], outputs=[8])
    if engine_flag:
        pip = PipelineEngine(cache=cache, safe_input_buffer_deepcopy=True)
    else:
        pip = PipelineCore(filters=[filt1, filt2], cache=cache, inputs=[input_image])
    expected_filt1 = (2*input_image - 3)
    # 1/ execute for the first time
    res = pip.run([filt1, filt2], imglst=[input_image]) if engine_flag else pip.run()
    if cache:
        assert filt1.cache_mem.state_change.update_needed
        assert filt2.cache_mem.state_change.update_needed

    assert (res[2] == expected_filt1).all()
    assert (res[8] == 0.4*input_image+0.6*expected_filt1).all()

    # 2/ do it again
    # cache shall be used for the two filters as no parameters were updated
    res = pip.run([filt1, filt2], imglst=[input_image]) if engine_flag else pip.run()
    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert not filt2.cache_mem.state_change.update_needed

    # 3/ change parameters of the second filter and go again
    # first filter shall use its cache, second filter needs reprocessing
    if engine_flag:
        filt2.values["blend_coeff"] = 0.8
    else:
        pip.parameters = {"blend": {"blend_coeff": 0.8}}
    res = pip.run([filt1, filt2], imglst=[input_image]) if engine_flag else pip.run()
    assert np.allclose(res[8], (0.8*input_image+0.2*expected_filt1))

    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert filt2.cache_mem.state_change.update_needed

    # 4/ do it once more, nothing has changed, cache is reused
    res = pip.run([filt1, filt2], imglst=[input_image]) if engine_flag else pip.run()
    assert np.allclose(res[8], (0.8*input_image+0.2*expected_filt1))
    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert not filt2.cache_mem.state_change.update_needed
