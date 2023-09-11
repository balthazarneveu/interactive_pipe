**Version 0.5.5**

# Concept
- Develop your algorithm while debugging with plots, while checking robustness & continuity to parameters change
- Tune your algorithms and save your parameters for later batch processing
- Ready to batch under the hood, the processing engine can be ran without GUI (therefore allowing to use the same code for tuning & batch processing if needed).


# Setup
`pip3 install -i https://test.pypi.org/simple/ interactive-pipe`   *:x: not officially on PyPi yet*


## :scroll:  Features
- Modular multi-image processing filters
- Easily make graphical user interface without having to learn anything about pyQt or matplotlib
- Support in jupyter notebooks
- Tuning sliders & check buttons  with a GUI
- Cache intermediate results in RAM for much faster processing
- `KeyboardControl` : no slider on UI but exactly the same internal mechanism, update on key press.
- Support Curve plots (2D signals)

### :soon: Upcoming features:
- :soon: Scientific visual debugging: Display both colored images, heatmaps & graphs


### :test_tube: Experimental features
- custom events on specific key press
- Display the execution graph of the pipeline
- [thirdparty/music](/src/interactive_pipe/thirdparty/music.py) Play audio (Qt backend only). Play songs on spotify (linux only) when the spotify app is running.
- [thirdparty/images_openai_api](/src/interactive_pipe/thirdparty/images_openai_api.py) Generate images from prompt using OpenAI API image generation DALL-E Model (:dollar:  paid service ~ 2cents/image) 

### :keyboard:   Keyboard shortcuts
Shortcuts while using the GUI (QT & matplotlib backends)

- `F1` to show the help shortcuts in the terminal
- `F11` toggle fullscreen mode
- `W` to write full resolution image to disk
- `R` to reset parameters
- `I` to print parameters dictionary in the command line
- `E` to export parameters dictionary to a yaml file
- `O` to import parameters dictionary from a yaml file (sliders will update)
- `G` to export a pipeline diagram for your interactive pipe (requires graphviz)



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



## :rocket: Ultra short code
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
:heart: This code shall display you a GUI with three images. The middle one is the result of the blend



Notes:
- If you write `def blend(img0, img1, blend_coeff=0.5):`, blend_coeff will simply not be a slider on the GUI no more.
- If you write `blend_coeff=[0., 1.]` , blend_coeff will be a slider initalized to 0.5
- If you write `bnw=(True, "black and white", "k")`, the checkbox will disappear and be replaced by a keypress event (press `k` to enable/disable black & white)

-----------
## :bulb: Some more tips

```python
from interactive_pipe import interactive, interactive_pipeline
import numpy as np

COLOR_DICT = {"red": [1., 0., 0.],  "green": [0., 1.,0.], "blue": [0., 0., 1.], "gray": [0.5, 0.5, 0.5]}
@interactive()
def generate_flat_colored_image(color_choice=["red", "green", "blue", "gray"], global_params={}):
    '''Generate a constant colorful image
    '''
    flat_array =  np.array(COLOR_DICT.get(color_choice)) * np.ones((64, 64, 3))
    global_params["avg"] = np.average(flat_array)
    return flat_array
```

- Note that you can also create filters which take no inputs and simply "generate" images. 
- The `color_choice` list will be turnt into a nice dropdown menu. Default value here will be red as this is the first element of the list!
----------

:bulb: Can filters communicate together?
Yes, using the special keyword argument `global_params={}`. 
- Check carefully how we stored the image average of the flat image in  global_params. 
- This value will be available to other filters.
`special_image_slice` is going to use that value to set the half bottom image to dark in case the average is high.

```python
@interactive()
def special_image_slice(img, global_params={}):
    if global_params["avg"] > 0.4:
        out_img[out_img.shape[0]//2:, ...] = 0.
    return out_img
```
---


```python
@interactive()
def switch_image(img1, img2, img3, image_index=(0, [0, 2], None, ["pagedown", "pageup", True])):
    '''Switch between 3 images
    '''
    return [img1, img2, img3][image_index]
```
Note that you can create a filter to switch between several images. In `["pagedown", "pageup", True]`, True means that the image_index will wrap around. (it will return to 0 as soon as it goes above the maximum value of 2).

```python
@interactive()
def black_top_image_slice(img, top_slice_black=(True, "special", "k"), global_params={}):
    out_img = img.copy()
    if top_slice_black:
        out_img[:out_img.shape[0]//2, ...] = 0.
    return out_img


@interactive_pipeline(gui="qt", size="fullscreen")
def sample_pipeline_generated_image():
    flat_img = generate_flat_colored_image()
    top_slice_modified = black_top_image_slice(flat_img)
    bottom_slice_modified_image = special_image_slice(flat_img)
    chosen = switch_image(flat_img, top_slice_modified, bottom_slice_modified_image)
    return chosen

if __name__ == '__main__':
    sample_pipeline_generated_image()
```

----------

### History
- Interactive pipe was initially developped by [Balthazar Neveu](https://github.com/balthazarneveu) as part of the [irdrone project](https://github.com/wisescootering/infrareddrone/tree/master/interactive) based on matplotlib.
- Later, more contributions were also made by [Giuseppe Moschetti](https://github.com/g-moschetti) and Sylvain Leroy.
- Summer 2023: rewriting the whole core and supporting several graphical backends!



# Roadmap and todos
:bug: Want to contribute or interested in adding new features? Enter a new [Github issue](https://github.com/balthazarneveu/interactive_pipe/issues)

:gift: Want to dig into the code? Take a look at [code_architecture.md](/code_architecture.md)

## Short term roadmap
- Backport previous features
    - Image class support in interactive pipe (Heatmaps/Float images)

## Long term roadmap
- Advanced feature
    - Webcam based "slider" for dropdown menu (like "elephant" will trigget if an elephant is magically detected on the webcam)
    - Animations/While loops/Video source (Time slider)
- Exploratory backends
    - Create a [textual](https://github.com/Textualize/textual) backend for simplified GUI (probably no images displayed)
    - Create a [Kivy](https://kivy.org/) backend