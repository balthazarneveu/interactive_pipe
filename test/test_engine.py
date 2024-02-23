import numpy as np
import pytest
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.engine import PipelineEngine
from interactive_pipe.core.pipeline import PipelineCore

input_image = np.array([[1, 2, 3], [4, 5, 6]])


def mad(img, coeff=2, bias=-3):
    mad_res = img*coeff+bias
    return [mad_res]


def mad_gp(img, global_params={}, coeff=2, bias=-3):
    assert "ratio" in global_params.keys(), "shall be set by an earlier filter"
    mad_res = (img*coeff+bias)
    global_params["ratio"] += 1  # JUST FOR PYTEST PURPOSE
    # WARNING, you shall never update global_params in this way (when using the cache)
    # Only if your parameters or your inputs changed, you can update global_params...
    # But twice the same input & parameters shall not modify the global_params.
    return [mad_res]


def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]


class Blend(FilterCore):
    def apply(self, img1, img2, blend_coeff=0.8):
        blended = (blend_coeff*img1+(1-blend_coeff)*img2)
        self.global_params["ratio"] += 2  # JUST FOR PYTEST PURPOSE
        return [blended]

# NOTE: tests both FilterCore & PipelineEngine & PipelineCore


@pytest.mark.parametrize("cache", [True, False])
@pytest.mark.parametrize("global_params_flag", [True, False])
def test_pipeline_params(cache, global_params_flag):
    filt1 = FilterCore(apply_fn=mad_gp if global_params_flag else mad,
                       name="mad", outputs=[2], default_params={"coeff": 1, "bias": 0})
    filt2 = FilterCore(apply_fn=blend, inputs=[0, 2], outputs=[8])
    pip = PipelineCore(filters=[filt1, filt2], inputs=[
                       0], cache=cache, global_params={"ratio": 5})
    assert pip.parameters["blend"] == {"blend_coeff": 0.4}
    assert pip.parameters["mad"] == {"coeff": 1, "bias": 0}
    expected_ratio = 5
    # updated the coefficients...  need to re-execute no matter cache or not
    assert pip.global_params["ratio"] == expected_ratio
    pip.inputs = [input_image]
    pip.run()
    assert pip.global_params["ratio"] == 6 if global_params_flag else 5
    # updated the coefficients...  need to re-execute no matter cache or not
    pip.parameters = {"mad": {"coeff": 2}}
    pip.run()
    assert pip.global_params["ratio"] == 7 if global_params_flag else 5
    # kept the same coefficients...  when cache is enable, we'll won't go into the mad filter again
    # please keep in mind that using a shared global_params & cache requires you to be very cautious.
    # usually, a change of parameters in one of the first filters triggers an update in the global_params.
    pip.run()
    assert pip.global_params["ratio"] == (
        7 if cache else 8) if global_params_flag else 5


@pytest.mark.parametrize("cache", [True, False])
def test_pipeline_mix(cache):
    filt1 = FilterCore(apply_fn=mad_gp, name="mad", outputs=[
                       2], default_params={"coeff": 1, "bias": 0})
    filt2 = Blend(inputs=[0, 2], outputs=[8])
    pip = PipelineCore(filters=[filt1, filt2], cache=cache, inputs=[
                       0], global_params={"ratio": 5})
    assert pip.parameters["Blend"] == {"blend_coeff": 0.8}
    assert pip.parameters["mad"] == {"coeff": 1, "bias": 0}
    pip.inputs = [input_image]
    pip.run()
    assert pip.global_params["ratio"] == 8
    pip.run()
    assert pip.global_params["ratio"] == 8 if cache else 11


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
        pip = PipelineCore(filters=[filt1, filt2], cache=cache, inputs=[0])
    expected_filt1 = (2*input_image - 3)
    # 1/ execute for the first time
    pip.inputs = [input_image]
    res = pip.run([filt1, filt2], imglst=[input_image]
                  ) if engine_flag else pip.run()
    if cache:
        assert filt1.cache_mem.state_change.update_needed
        assert filt2.cache_mem.state_change.update_needed

    assert (res[2] == expected_filt1).all()
    assert (res[8] == 0.4*input_image+0.6*expected_filt1).all()

    # 2/ do it again
    # cache shall be used for the two filters as no parameters were updated
    res = pip.run([filt1, filt2], imglst=[input_image]
                  ) if engine_flag else pip.run()
    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert not filt2.cache_mem.state_change.update_needed

    # 3/ change parameters of the second filter and go again
    # first filter shall use its cache, second filter needs reprocessing
    if engine_flag:
        filt2.values["blend_coeff"] = 0.8
    else:
        pip.parameters = {"blend": {"blend_coeff": 0.8}}
    res = pip.run([filt1, filt2], imglst=[input_image]
                  ) if engine_flag else pip.run()
    assert np.allclose(res[8], (0.8*input_image+0.2*expected_filt1))

    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert filt2.cache_mem.state_change.update_needed

    # 4/ do it once more, nothing has changed, cache is reused
    res = pip.run([filt1, filt2], imglst=[input_image]
                  ) if engine_flag else pip.run()
    assert np.allclose(res[8], (0.8*input_image+0.2*expected_filt1))
    if cache:
        assert not filt1.cache_mem.state_change.update_needed
        assert not filt2.cache_mem.state_change.update_needed
