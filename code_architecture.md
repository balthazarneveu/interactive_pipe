# Code architecture
The following document allows you to understand how the `interactive_pipe` library is designed if you want to dig in or contribute to it.

:soon: This logo means some feature are coming in the near future.

:warning: Undocumented decorators as there may still be some changes. 

# High level view
## Core
Core of the library to define pure pipeline processings & parameters controls in a class oriented fashion.
- [`PureFilter`](/src/interactive_pipe/core/filter.py): The most minimalistic filter object used to execute the user defined `apply_fn` based on the `.values` dictionary stored as a class member.
- [`FilterCore`](/src/interactive_pipe/core/filter.py) adds two features to the `PureFilter`: 
    - the routing mechanism needed to interconnect several filters in a pipeline
    - a cache `.cache_mem` to store the result of previous execution. `CachedResults` uses `StateChange` to check whether or not parameters have been updated.
- [`Control`](/src/interactive_pipe/core/control.py) and [`KeyboardControl`](/src/interactive_pipe/core/keyboard.py) define how a parameter can vary (default_value, range, step, which key to press). In the graphical interface, these controls will later be interpreted & materialized as widgets (slider, buttons, checkboxes) or a keyboard interaction.
- [`PipelineCore`](/src/interactive_pipe/core/pipeline.py) is defined by a sequence of filters interconnected to each other through a routing definition. Pipeline execution is performed using a [`PipelineEngine`](src/interactive_pipe/core/engine.py) which will:
    - simply take the outputs from previous filters and feed it to the next filter's `.apply_fn` and provide the updated parameters.
    - deal with the cache mechanism to avoid unnecessary computations.


## Headless
This is called headless as it is still not related to graphical user interface.
- [`HeadlessPipeline`](/src/interactive_pipe/headless/pipeline.py) extends `PipelineCore` with useful features
    - saving results to disk / loading results & parameters from disk 
    - visualizing execution graphs (*requires graphviz*)
    - initialize a pipeline from a function. This is one of the powerful features of `interactive_pipe` which allows defining a pipeline & its routing mechanism from a single function (+all filters defined as functions only).

## Data objects
[`Data`](/src/interactive_pipe/data_objects/data.py) is a generic class which allows reducing boiler plate code when dealing with file paths. Here are the following implementations
- [`Parameters`](/src/interactive_pipe/data_objects/parameters.py) class is used to store/reload dictionaries (usually pipeline parameters) to disk, it supports json & [yaml](https://pypi.org/project/PyYAML/) formats.
- [`Image`](/src/interactive_pipe/data_objects/image.py) class deals with loading/saving images from disk (using [PIL](https://pypi.org/project/Pillow/) *by default* or [cv2](https://pypi.org/project/opencv-python/) if available). Internal data is stored using [numpy arrays](https://pypi.org/project/numpy/) and by default images are normalized in the [0, 1] range and stored as float32 so this can be an assumption throughout the whole pipeline.


## Graphical
- Currently supported backends:
    - `qt` based on either PySide or PyQt depending on what you have.
    - `mpl` matplotlib used for scientific visualization.
    - `nb` based on [ipywidgets](https://ipywidgets.readthedocs.io/en/stable/) used in jupyter notebooks.

Note: [`InteractivePipeGUI`](/src/interactive_pipe/graphical/gui.py) & [`InteractivePipeWindow`](/src/interactive_pipe/graphical/gui.py) have to be defined for each backend.



# Detailed description
## Core
An pure pipeline execution without graphical interface related stuffs
### [`filter.py`](/src/interactive_pipe/core/filter.py) & [`signature.py`](/src/interactive_pipe/core/signature.py)
- `PureFilter`: The most minimalistic filter object used to execute the user defined `apply_fn`. Keyword arguments of `apply_fn` are provided through parameters stored as the data member `.values`.
    - Allows to `.run` the `apply_fn` based on the `.values` dictionary. 
    - To update parameters, you need to update `.values` which will merge the new parameters with the previous parameters.
    - Uses a special keryword arg `global_params` to carry over context information between different filters.
    - [`analyze_apply_fn_signature`](/src/interactive_pipe/core/signature.py) allows to analyze the `.apply_fn` to check if provided keyword parameters match what's written in the function. The [inspect](https://docs.python.org/3/library/inspect.html) library is used to check the function's signature.
- `FilterCore(PureFilter)`
    - Adds the routing definition (requires `.inputs` & `.outputs`). In a pipeline, this allows to tell how to inter-connect several filters together.
    - Adds a `.cache_mem` instance of `CachedResults` to store the result of previous execution.
    - *Note that cached update check (StateChange) is not actually used inside the run function.* It comes at the pipeline level. For some simple reason: the filter could check if the parameters have been updated... but it's far more difficult to check if the input changed when executing (without recomputing a hash every time which can be burdensome). In a pipeline scenario: the most elegant way is to inform the current filter instance that its inputs have been modified by previous filters... simply if previous filters have updated their results...
    
### [`cache.py`](/src/interactive_pipe/core/cache.py)
- `CachedResults`: helper class to store the results of a Filter. 
    - Uses `StateChange` to monitor the parameters update.
    - Each Filter has its own CachedResults class
        - uses a StateChange to detect if parameters/sliders values have been modified
        - update results only when the state of the sliders has been changed
        - keep cached Filters results in memory
    - Please note that if you use `safe_buffer_deepcopy=False`, only pointers are copied when updating the cache, no deepcopy is performed here. You should only use safe_buffer_deepcopy=False if you're 100% sure you don't do inplace modifications. To avoid mistake, it's been set to True by default although it will take more RAM.
- `StateChange`: helper class to check whether or not input parameters have been updated.


### [`control.py`](/src/interactive_pipe/core/control.py) and [`keyboard.py`](/src/interactive_pipe/core/keyboard.py)
- [`Control`](/src/interactive_pipe/core/control.py) 
    - Defines a parameter by its `.value_default` and it's potential variations (`.value_range`) and (`.step`). 
    - Supported types are:
        - `int` /`float` later materialized as a slider
        - `bool` later materialized as a checkbox 
        - `str` later materialized as a dropdown menu.
- [`KeyboardControl(Control)`](/src/interactive_pipe/core/keyboard.py)
    - extends a `Control` by defining two keyboard keys to increase / decrease a parameter. 
    - the `.modulo` attributes allows "wrapping around" the parameter (when you go above the maximum/end, you'll come back to the mininum/start, and vice versa). This can be handy for instance if you're switching between a few images with pageup/pagedown.
    - When using a bool, a single key is required to turn on/off the parameter.

### [`pipeline.py`](/src/interactive_pipe/core/pipeline.py) & [`engine.py`](src/interactive_pipe/core/engine.py)
[`PipelineCore`](/src/interactive_pipe/core/pipeline.py) is defined by a sequence of filters interconnected to each other through a routing definition. Execution is performed using a [`PipelineEngine`](src/interactive_pipe/core/engine.py) which will simply take the outputs from previous filters and feed it to the next filter `apply_fn`.
- [`PipelineCore`](/src/interactive_pipe/core/pipeline.py) :
    - takes care of parameters updates & reset (then to dispatch the updated parameters to each filter)
    - stores the inputs provided to the pipeline & deals with inputs updates.
- [`PipelineEngine`](src/interactive_pipe/core/engine.py)
    - applies the defined routing (basically a execution graph)
    - takes care of the cache mechanism.
    - *No support of parallellism / threading, filters are computed sequentially*

## data_objects

### [`Data`](/src/interactive_pipe/data_objects/data.py)
`Data` is a generic class which allows reducing boiler plate code when dealing with file paths:
- specifying a set of file extensions.
- saving files to disk by creating the right folder parents & adding the right extensions if not provided by the user.
- checking that a file exists before loading.
- loading files from a prompted path (:soon: from a dialog menu)

Data class has to be re-implemented everytime.  `._set_file_extensions`, `._save`, `._load` .

### [`Parameters`](/src/interactive_pipe/data_objects/parameters.py)
`Parameters` class is used to store/reload dictionaries (usually pipeline parameters) to disk.
- Supports json & [yaml](https://pypi.org/project/PyYAML/) formats.

### [`Image`](/src/interactive_pipe/data_objects/image.py)
`Image` class deals with loading/saving images from disk.
It uses whatever image is available to save images (among [PIL](https://pypi.org/project/Pillow/) *by default* & [cv2](https://pypi.org/project/opencv-python/))
- internal data is stored using [numpy arrays](https://pypi.org/project/numpy/) and by default images are normalized in the [0, 1] range and stored as float32 so this can be an assumption throughout the whole pipeline.
- :soon: This code is expected to be extended to support pytorch tensors, moving data to/from GPU seamlessly when needed (when saving or visualizing to screen, not after each filter to avoid polluting the code...).
- it has a `.show()` method, useful inside a jupyter notebook

## graphical
- Currently supported backends:
    - `qt` based on either PySide or PyQt depending on what you have.
    - `mpl` matplotlib used for scientific visualization.
    - `nb` based on [ipywidgets](https://ipywidgets.readthedocs.io/en/stable/) used in jupyter notebooks.



| `qt`  | `mpl`  | `nb`  | Feature                                                 |
|:-----:|:------:|:----: |:------------------------------------------------------- |
| :ok:  |  :x:   |  :x:  | Audio support                                           |
| :question:   | :soon: | :soon:| 1D Signal plot                                          |
| :question:   | :soon: | :soon:| Image Titles                                            |
| :ok:  |  :x:   |  :x:  | `Controls` string list  with image icons                |
| :ok:  |  :ok:  |  :x:  |Keyboard shortcuts to reset sliders, save to disk etc... |
| :ok:  |  :ok:  |  :x:  | `KeyboardControl`                                       |
| :ok:  |  :x:   |  :x:  | F11 toggle full screen                                  |
| :ok:  |  :ok:  |  :ok: | `size=(w, h)`                                           |
| :ok:  |  :ok:  |  :x:  | `size="fullscreen"`                                     |
| :ok:  |  :x:   |  :x:  | `size="maximized"`                                      |
| :ok:  |  :ok:  |  :ok: | Refresh UI on canvas change                             |
| :ok:  |  :ok:  |  :ok: | Float sliders                                           |
| :ok:  |  :ok:  |  :ok: | `Controls` int / float sliders                          |
| :ok:  |  :ok:  |  :ok: | `Controls` bool checkbox                                |
| :ok:  |  :ok:  |  :ok: | `Controls` string list dialog menu / radio buttons      |

Note: `InteractivePipeGUI` & `InteractivePipeWindow` have to be defined for each backend.

- [`InteractivePipeGUI`](/src/interactive_pipe/graphical/gui.py) is the main app. 
    - It deals with key bindings (keyboard press triggers a function. function docstring is shown to the user when he presses "F1" help)
    - it deals with printing the help 
- [`InteractivePipeWindow`](/src/interactive_pipe/graphical/gui.py) is the window which displays the results & the sliders.
    - `.size` = `(w, h)`/ `fullscreen` / `maximized` defines the user expected window size.
    - It deals with the graphical refresh
    - It allows to refreshes the canvas (displaying two images side by side or four images in a 2x2 square fashion for instance.)


| `qt`  | `mpl`  | `nb`  | |
|:-----:|:------:|:----: | :---- | 
| `InteractivePipeQT` | `InteractivePipeMatplotlib` | `InteractivePipeJupyter` | GUI Class name |
| [qt_control.py](/src/interactive_pipe/graphical/qt_gui.py)   | [mpl_gui.py](/src/interactive_pipe/graphical/mpl_gui.py) | [nb_gui.py](/src/interactive_pipe/graphical/nb_gui.py) | Code for GUI & Window |
| [qt_control.py](/src/interactive_pipe/graphical/qt_control.py) | [mpl_control.py](/src/interactive_pipe/graphical/mpl_control.py) | [nb_control.py](/src/interactive_pipe/graphical/nb_control.py) | Code for widget controls|

## thirparty
Some helpful helpers based on paid services
### [`ImageFromPrompt`](src/interactive_pipe/thirdparty/images_openai_api.py) 
Extends the `Image` class to generate images from a text prompt using the OpenAI Dall-E online API, store to disk & directly load to memory as a numpy array.
- requires [`openai`](https://pypi.org/project/openai/) library  installed
- :dollar:  requires an API account
### [`get_spotify_music()`](src/interactive_pipe/thirdparty/music_spotify.py) 
Allows you to acess the Spotify interface.
- :dollar: requires the spotify app to be running & the user to be logged in
- requires the `dbus` library, only supported under linux right now. *Use `apt-get install -y dbus` in sudo mode.*
- In spotify, right click on a song, "share", "copy song link".
```python
spotify_music = get_spotify_music()
spotify_music.set_audio('https://open.spotify.com/track/15VRO9CQwMpbqUYA7e6Hwg?si=bdc9ff37d5af4bb1')
```