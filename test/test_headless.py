import numpy as np
import pytest
from copy import deepcopy

try:
    from interactive_pipe.core.filter import FilterCore
    from interactive_pipe.core.engine import PipelineEngine
    from interactive_pipe.core.pipeline import PipelineCore
    from interactive_pipe.headless.pipeline import HeadlessPipeline
    from interactive_pipe.data_objects.image import Image
except:
    import helper
    from core.filter import FilterCore
    from core.engine import PipelineEngine
    from core.pipeline import PipelineCore
    from headless.pipeline import HeadlessPipeline
    from data_objects.image import Image


def mad(img, coeff=1, bias=0.):
    mad_res = img*coeff+bias
    return [mad_res]



def blend(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [blended]

def blend_image_out(img1, img2, blend_coeff=0.4):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return [Image(blended, title=f"blend={blend_coeff:0.2f}")]


def get_sample_image():
    img = 0.5*np.ones((256, 512, 3))
    img[:, 100:, 0] *= 0.5
    img[150:, :, 2] *= 1.5
    img[:200, :, :] *= 0.5
    return img

def test_headless_pipeline():
    input_image = get_sample_image()
    filt1 = FilterCore(apply_fn=mad, name="mad", outputs=[1])
    filt2 = FilterCore(apply_fn=blend, inputs=[0, 1], outputs=[6])
    pip = HeadlessPipeline(filters=[filt1, filt2], inputs=[input_image], global_params={"ratio": 5})
    pip.save("_image.png", data_wrapper_fn=lambda x: Image(x))


def test_headless_pipeline_outputs_images(tmp_path_factory):
    input_image = get_sample_image()
    filt1 = FilterCore(apply_fn=mad, name="mad", outputs=[1])
    filt2 = FilterCore(apply_fn=blend_image_out, inputs=[0, 1], outputs=[6])
    pip = HeadlessPipeline(filters=[filt1, filt2], inputs=[input_image], global_params={"ratio": 5})
    out_path = tmp_path_factory.mktemp("data")
    assert out_path.exists()
    pip.save(out_path/"_image_from_Image_class.png")
    pip.export_tuning(out_path/"tuning/tuning.yaml")
    pip.import_tuning(out_path/"tuning/tuning.yaml")
