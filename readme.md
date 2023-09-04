**Version 0.4**

# Concept
- Develop your algorithm while debugging with plots, while checking robustness & continuity to parameters change
- Tune your algorithms and save your parameters for later batch processing
- Ready to batch under the hood, the processing engine can be ran without GUI (therefore allowing to use the same code for tuning & batch processing if needed).

# Setup
`pip3 install -i https://test.pypi.org/simple/ interactive-pipe`   *:x: not officially on PyPi yet*

# Status
- supported backends 
    - :ok: `gui='qt'` pyQt/pySide 
    - :ok: `gui='mpl'` matplotlib
    - :ok: `gui='nb'`  ipywidget for jupyter notebooks  
- tested platforms
    - :ok: Linux (Ubuntu / KDE Neon)
    - :ok: RapsberryPi
    - :ok: On google collab (use `gui='nb'`)

# Tutorial
*Since ipywidgets in notebooks are supported, the tutorial is also available in a [google collab notebook](https://colab.research.google.com/drive/1PZn8P_5TABVCugT3IcLespvZG-gxnFbO?usp=sharing)*



## Ultra short code
Let's define 3 image processing very basic filters `exposure`, `black_and_white` & `blend`.

By design:
- image buffers inputs are arguments
- keyword arguments are the parameters which can be later turned into interactive widgets.
- output buffers are simply returned like you'd do in a regular function.

We use the `@interactive()` wrapper which will turn each keyword parameters initialized to a **tuple/list** into a graphical interactive widgets (slider, tick box, dropdown men). 

The syntax to turn keyword arguments into sliders is pretty simple `(default, [min, max], name)` will turn into a float slider for instance.

Finally, we need to the glue to combo these filters. This is where the sample_pipeline function comes in.

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

@interactive_pipeline(gui="qt")
def sample_pipeline(input_image):
    exposed = exposure(input_image)
    bnw_image = black_and_white(input_image)
    blended  = blend(exposed, bnw_image)
    return exposed, blended, bnw_image

if __name__ == '__main__':
    input_image = np.array([0., 0.5, 0.8])*np.ones((256, 512, 3))
    sample_pipeline(input_image)

```
:heart: This code shall display you a GUI with three images. The middle one is the result of the blend

> Note: If you write `def blend(img0, img1, blend_coeff=0.5):`, blend_coeff will simply not be a slider on the GUI no more.




# Roadmap and todos
Want to contribute or interested in adding new features? Enter a new [Github issue](https://github.com/balthazarneveu/interactive_pipe/issues)
- Routing mechanism based on keys rather than indexes (switch from list to dict)
- Backport previous features
    - 2D signal plots & signal class
    - keyboard sliders press
- Advanced feature
    - Webcam based "slider" for dropdown menu (like "elephant" will trigget if an elephant is magically detected on the webcam)
    - Animations/While loops/Video source (Time slider)
- Exploratory backends
    - Create a [textual](https://github.com/Textualize/textual) backend for simplified GUI (probably no images displayed)
    - Create a [Kivy](https://kivy.org/) backend