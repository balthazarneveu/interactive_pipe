# Quick Start

## Installation

### From PyPI

```bash
pip install interactive-pipe
```

### Local Development Setup

```bash
git clone git@github.com:balthazarneveu/interactive_pipe.git
cd interactive-pipe
pip install -e ".[full]"
```

## Your First Interactive Pipeline

Let's define 3 image processing very basic filters: `exposure`, `black_and_white` & `blend`.

By design:
- Image buffer inputs are arguments
- Keyword arguments are the parameters which can be later turned into interactive widgets
- Output buffers are simply returned like you'd do in a regular function

We use the `@interactive()` wrapper which will turn each keyword parameters initialized to a **tuple/list** into a graphical interactive widget (slider, tick box, dropdown menu). 

The syntax to turn keyword arguments into sliders is pretty simple: `(default, [min, max], name)` will turn into a float slider for instance.

Finally, we need the glue to combo these filters. This is where the `sample_pipeline` function comes in.

By decorating it with `@interactive_pipeline(gui="qt")`, calling this function will magically turn into a GUI powered image processing pipeline.

```python
from interactive_pipe import interactive, interactive_pipeline
import numpy as np

@interactive()
def exposure(img, coeff = (1., [0.5, 2.], "exposure"), bias=(0., [-0.2, 0.2])):
    '''Applies a multiplication by coeff & adds a constant bias to the image'''
    # In the GUI, the coeff will be labelled as "exposure". 
    # As the default tuple provided to bias does not end up with a string, 
    # the widget label will be "bias", simply named after the keyword arg. 
    return img*coeff + bias


@interactive()
def black_and_white(img, bnw=(True, "black and white")):
    '''Averages the 3 color channels (Black & White) if bnw=True
    '''
    # Special mention for booleans: using a tuple like (True,) allows creating the tick box.
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img

@interactive()
def blend(img0, img1, blend_coeff=(0.5, [0., 1.])):
    '''Blends between two image. 
    - when blend_coeff=0 -> image 0  [slider to the left ] 
    - when blend_coeff=1 -> image 1   [slider to the right] 
    '''
    return  (1-blend_coeff)*img0+ blend_coeff*img1

# you can change the backend to mpl instead of Qt here.
@interactive_pipeline(gui="qt", size="fullscreen")
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended  = blend(exposed, bnw_image)
    return exposed, blended, bnw_image

if __name__ == '__main__':
    input_image = np.array([0., 0.5, 0.8])*np.ones((256, 512, 3))
    sample_pipeline(input_image)
```

❤️ This code shall display you a GUI with three images. The middle one is the result of the blend.

## Parameter Variations

Notes:
- If you write `def blend(img0, img1, blend_coeff=0.5):`, blend_coeff will simply not be a slider on the GUI.
- If you write `blend_coeff=[0., 1.]`, blend_coeff will be a slider initialized to 0.5
- If you write `bnw=(True, "black and white", "k")`, the checkbox will disappear and be replaced by a keypress event (press `k` to enable/disable black & white)

## Next Steps

- Learn more in our [User Guide](../guide/filters.md)
- Explore [Tutorials](tutorials.md)
- Check out the [API Reference](../api/core.md)
