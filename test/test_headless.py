import shutil
import pytest
import numpy as np
from sample_functions import get_sample_image
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.data_objects.image import Image


def mad(img, coeff=1, bias=0.):
    mad_res = img*coeff+bias
    return [mad_res]


def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]


def blend_image_out(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [Image(blended, title=f"blend={blend_coeff:0.2f}")]


def generate_uniform(gray_level=0.5):
    return gray_level*np.ones((5, 5, 3))


def test_headless_pipeline(tmp_path_factory):
    input_image = get_sample_image()
    filt1 = FilterCore(apply_fn=mad, name="mad", outputs=[1])
    filt2 = FilterCore(apply_fn=blend, inputs=[0, 1], outputs=[6])
    pip = HeadlessPipeline(filters=[filt1, filt2], inputs=[
                           0], global_params={"ratio": 5})
    pip.inputs = [input_image]
    out_path = tmp_path_factory.mktemp("data_1")
    assert out_path.exists()
    pip.save(out_path/"_image.jpg", data_wrapper_fn=lambda x: Image(x))
    shutil.rmtree(out_path)  # clean  temporary folder


def test_headless_pipeline_outputs_images(tmp_path_factory):
    input_image = get_sample_image()
    filt1 = FilterCore(apply_fn=mad, name="mad", outputs=[1])
    filt2 = FilterCore(apply_fn=blend_image_out, inputs=[0, 1], outputs=[6])
    pip = HeadlessPipeline(filters=[filt1, filt2], inputs=[
                           0], global_params={"ratio": 5})
    pip.inputs = [input_image]
    out_path = tmp_path_factory.mktemp("data_2")
    assert out_path.exists()
    pip.save(out_path/"_image_from_Image_class.png")
    pip.export_tuning(out_path/"tuning/tuning.yaml")
    pip.import_tuning(out_path/"tuning/tuning.yaml")
    shutil.rmtree(out_path)  # clean  temporary folder


@pytest.mark.parametrize("routing_indexes", [True, False])
def test_headless_pipeline_single_input(routing_indexes):
    input_image = get_sample_image()
    if routing_indexes:
        IMG_IN = 0
        MAD_OUT = 1
        BLEND_OUT = 6
    else:
        IMG_IN = "image_in"
        MAD_OUT = "exposed"
        BLEND_OUT = "blended"
    filt1 = FilterCore(apply_fn=mad, name="mad", inputs=[
                       IMG_IN], outputs=[MAD_OUT])
    filt2 = FilterCore(apply_fn=blend, inputs=[
                       IMG_IN, MAD_OUT], outputs=[BLEND_OUT])
    pip = HeadlessPipeline(filters=[filt1, filt2], inputs=[
                           IMG_IN], global_params={"ratio": 5}, cache=True)
    pip.inputs = input_image
    pip.run()
    assert filt1.cache_mem.state_change.update_needed
    assert filt2.cache_mem.state_change.update_needed
    pip.run()
    assert not filt1.cache_mem.state_change.update_needed
    assert not filt2.cache_mem.state_change.update_needed
    # Setting new inputs means cache will be cleared.
    pip.inputs = (input_image,)
    pip.run()
    assert filt1.cache_mem.state_change.update_needed
    assert filt2.cache_mem.state_change.update_needed
    pip.run()
    assert not filt1.cache_mem.state_change.update_needed
    assert not filt2.cache_mem.state_change.update_needed
    # by calling the function, we force to update inputs
    pip(0.5*input_image)
    assert filt1.cache_mem.state_change.update_needed
    assert filt2.cache_mem.state_change.update_needed
    with pytest.raises(AssertionError):
        pip(0.5*input_image, input_image)
    with pytest.raises(AssertionError):
        pip()
    with pytest.raises(AssertionError):
        pip(inputs={"toto": input_image})
    pip(inputs={IMG_IN: input_image})


@pytest.mark.parametrize("routing_indexes", [True, False])
def test_headless_pipeline_multi_input(routing_indexes):
    input_image = get_sample_image()
    if routing_indexes:
        IMG_IN_1 = 0
        IMG_IN_2 = 2
        MAD_OUT = 4
        BLEND_OUT = 8
    else:
        IMG_IN_1 = "image_1"
        IMG_IN_2 = "image_2"
        MAD_OUT = "exposed"
        BLEND_OUT = "blended"
    filt1 = FilterCore(apply_fn=blend, inputs=[
                       IMG_IN_1, IMG_IN_2], outputs=[BLEND_OUT])
    filt2 = FilterCore(apply_fn=mad, name="mad", inputs=[
                       IMG_IN_1], outputs=[MAD_OUT])
    with pytest.raises(AssertionError):
        # no inputs routing provided
        pip = HeadlessPipeline(filters=[filt1, filt2], inputs=None, outputs=[
                               BLEND_OUT, MAD_OUT], cache=True)
        out = pip.run()

    with pytest.raises(AssertionError):
        # no inputs routing provided, still try to execute with two images
        pip = HeadlessPipeline(filters=[filt1, filt2], inputs=None, outputs=[
                               BLEND_OUT, MAD_OUT], cache=True)
        out = pip(input_image, 0.5*input_image)

    pip = HeadlessPipeline(filters=[filt1, filt2], inputs=[
                           IMG_IN_1, IMG_IN_2], outputs=[BLEND_OUT, MAD_OUT], cache=True)
    pip.inputs = input_image, 0.5*input_image
    out = pip.run()
    assert len(out) == 2
    pip(inputs={IMG_IN_2: 0.3*input_image, IMG_IN_1: input_image})
    with pytest.raises(AssertionError):
        pip(inputs={IMG_IN_2: input_image})


def test_headless_pipeline_no_input():
    input_image = get_sample_image()
    FLAT = "flat"
    MAD_OUT = "exposed"
    BLEND_OUT = "blended"
    filt1 = FilterCore(apply_fn=generate_uniform, inputs=None, outputs=[FLAT])
    filt2 = FilterCore(apply_fn=mad, name="mad",
                       inputs=[FLAT], outputs=[MAD_OUT])
    filt3 = FilterCore(apply_fn=blend, inputs=[
                       FLAT, MAD_OUT], outputs=[BLEND_OUT])

    pip = HeadlessPipeline(filters=[filt1, filt2, filt3], inputs=None, outputs=[
                           FLAT, BLEND_OUT, MAD_OUT], cache=True)
    pip()

    pip = HeadlessPipeline(filters=[filt1, filt2, filt3], inputs=[], outputs=[
                           FLAT, BLEND_OUT, MAD_OUT], cache=True)
    pip()

    pip = HeadlessPipeline(filters=[filt1, filt2, filt3], inputs=[], outputs=[
                           FLAT, BLEND_OUT, MAD_OUT], cache=True)
    pip.inputs = None
    out = pip.run()

    pip.inputs = []
    out = pip.run()
    assert len(out) == 3
