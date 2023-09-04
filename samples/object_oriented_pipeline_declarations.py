from interactive_pipe.headless.pipeline import HeadlessPipeline
from interactive_pipe.core.filter import FilterCore
import numpy as np
#-------------------------------------------------------------------------------------------------
def mad_func(img, coeff = 50, bias=0):
    mad_res = img*coeff/100.+ bias/100.
    return mad_res

#-------------------------------------------------------------------------------------------------
def black_and_white(img, bnw=False):
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img


#-------------------------------------------------------------------------------------------------
def blend(img1, img2, blend_coeff=0.5):
    blended = blend_coeff*img1+(1-blend_coeff)*img2
    return blended

#-------------------------------------------------------------------------------------------------

def named_based_routing():
    # Pretty painstaking job to define a pipeline this way.
    # But you're making sure that you know what you're doing
    mad_filter = FilterCore(mad_func, inputs=["my_inp"], outputs=["reexposed"])
    black_and_white_filter = FilterCore(black_and_white, inputs=["reexposed"], outputs=["bnw"])
    blend_filter = FilterCore(blend, inputs=["reexposed", "bnw"], outputs=["blended"])
    pipeline_list = [mad_filter, black_and_white_filter, blend_filter]
    pipeline = HeadlessPipeline(
        pipeline_list,
        name="pipeline with fully named buffered",
        inputs=["my_inp"],
        outputs=["my_inp", "reexposed", "blended"]
    )
    return pipeline
    
   
if __name__ == '__main__':
    def get_sample_image():
        img = np.array([0.1, 0.5, 0.8])*np.ones((1, 1, 3))
        return img
    pipeline = named_based_routing()
    try:
        pipeline.graph_representation(view=True, ortho=False) # you can already visualize the execution graph
    except:
        print("Graphviz was probably not found, ignoring")
        pass
    print(pipeline)
    image_in = get_sample_image()
    out = pipeline(image_in, bnw=False)
    print(pipeline)
    print(out)
