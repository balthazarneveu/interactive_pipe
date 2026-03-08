# Code Architecture

The following document allows you to understand how the `interactive_pipe` library is designed if you want to dig in or contribute to it.

## High Level View

- **core**: *Function classes*
    - These classes are supposed to run without any terminal access, interaction, user interaction or even hard drive accesses.
    - Build a `PipelineCore` from a list of `FilterCore`
   
- **headless**: *Adds I/O features & keyboard interactions & useful helpers to simplify things*
    - These classes are supposed to simplify pipeline declaration & allow you to control the pipeline from a terminal (like a server without screen or X11 forwarding).
    - Parameters variation range can be defined with `Controls`
    - Add keyboard controls
    - Allow loading/saving images & parameters from/to disk

- **graphical**: *Adds a GUI to headless pipeline*
    - Requires a computer screen or a remote machine with X11 forwarding.
    - Supports `qt` (pyqt or pyside), `mpl` (matplotlib), `nb` (jupyter notebooks) backends

## Core Module

Core of the library to define pure pipeline processings & parameters controls in a class-oriented fashion.

### Filter Classes

- [`PureFilter`](/src/interactive_pipe/core/filter.py): The most minimalistic filter object used to execute the user defined `apply_fn` based on the `.values` dictionary stored as a class member.

- [`FilterCore`](/src/interactive_pipe/core/filter.py) adds two features to the `PureFilter`: 
    - The routing mechanism needed to interconnect several filters in a pipeline
    - A cache `.cache_mem` to store the result of previous execution. `CachedResults` uses `StateChange` to check whether or not parameters have been updated.

### Pipeline Classes

- [`PipelineCore`](/src/interactive_pipe/core/pipeline.py) is defined by a sequence of filters interconnected to each other through a routing definition. Pipeline execution is performed using a [`PipelineEngine`](/src/interactive_pipe/core/engine.py) which will:
    - Simply take the outputs from previous filters and feed it to the next filter's `.apply_fn` and provide the updated parameters.
    - Deal with the cache mechanism to avoid unnecessary computations.

### Detailed Descriptions

#### filter.py & signature.py

- `PureFilter`: The most minimalistic filter object used to execute the user defined `apply_fn`. Keyword arguments of `apply_fn` are provided through parameters stored as the data member `.values`.
    - Allows to `.run` the `apply_fn` based on the `.values` dictionary. 
    - To update parameters, you need to update `.values` which will merge the new parameters with the previous parameters.
    - Uses a special keyword arg `global_params` to carry over context information between different filters.
    - [`analyze_apply_fn_signature`](/src/interactive_pipe/core/signature.py) allows analyzing the `.apply_fn` to check if provided keyword parameters match what's written in the function. The [inspect](https://docs.python.org/3/library/inspect.html) library is used to check the function's signature.

- `FilterCore(PureFilter)`
    - Adds the routing definition (requires `.inputs` & `.outputs`). In a pipeline, this allows telling how to inter-connect several filters together.
    - Adds a `.cache_mem` instance of `CachedResults` to store the result of previous execution.

#### cache.py

- `CachedResults`: Helper class to store the results of a Filter. 
    - Uses `StateChange` to monitor the parameters update.
    - Each Filter has its own CachedResults class
        - Uses a StateChange to detect if parameters/sliders values have been modified
        - Update results only when the state of the sliders has been changed
        - Keep cached Filters results in memory
    - Note: If you use `safe_buffer_deepcopy=False`, only pointers are copied when updating the cache, no deepcopy is performed. You should only use `safe_buffer_deepcopy=False` if you're 100% sure you don't do inplace modifications.

- `StateChange`: Helper class to check whether or not input parameters have been updated.

#### pipeline.py & engine.py

[`PipelineCore`](/src/interactive_pipe/core/pipeline.py) is defined by a sequence of filters interconnected to each other through a routing definition. Execution is performed using a [`PipelineEngine`](/src/interactive_pipe/core/engine.py) which will simply take the outputs from previous filters and feed it to the next filter `apply_fn`.

- [`PipelineCore`](/src/interactive_pipe/core/pipeline.py):
    - Takes care of parameters updates & reset (then dispatches the updated parameters to each filter)
    - Stores the inputs provided to the pipeline & deals with inputs updates.

- [`PipelineEngine`](/src/interactive_pipe/core/engine.py):
    - Applies the defined routing (basically an execution graph)
    - Takes care of the cache mechanism.
    - No support of parallelism / threading, filters are computed sequentially

## Headless Module

This is called headless as it is still not related to graphical user interface.

### HeadlessPipeline

[`HeadlessPipeline`](/src/interactive_pipe/headless/pipeline.py) extends `PipelineCore` with useful features:
- Saving results to disk / loading results & parameters from disk 
- Visualizing execution graphs (requires graphviz) with `.graph_representation`. This works particularly well in jupyter notebooks.
- Initialize a pipeline from a function. This is one of the powerful features of `interactive_pipe` which allows defining a pipeline & its routing mechanism from a single function (+all filters defined as functions only).
- You need to set the inputs before calling `.run`. A simpler way to do this is to use the `.__call__` method instead so you can use the pipeline as if it was a normal function.

### Control Classes

#### Control

[`Control`](/src/interactive_pipe/headless/control.py) defines a parameter by its `.value_default` and its potential variations (`.value_range`) and (`.step`). 

Supported types are:
- `int` / `float` later materialized as a slider
- `bool` later materialized as a checkbox 
- `str` later materialized as a dropdown menu

#### KeyboardControl

[`KeyboardControl`](/src/interactive_pipe/headless/keyboard.py) extends a `Control` by defining two keyboard keys to increase/decrease a parameter. 

- The `.modulo` attribute allows "wrapping around" the parameter (when you go above the maximum/end, you'll come back to the minimum/start, and vice versa). This can be handy for instance if you're switching between a few images with pageup/pagedown.
- When using a bool, a single key is required to turn on/off the parameter.

## Data Objects Module

### Data

[`Data`](/src/interactive_pipe/data_objects/data.py) is a generic class which allows reducing boilerplate code when dealing with file paths:
- Specifying a set of file extensions
- Saving files to disk by creating the right folder parents & adding the right extensions if not provided by the user
- Checking that a file exists before loading
- Loading files from a prompted path

Data class has to be re-implemented every time: `._set_file_extensions`, `._save`, `._load`.

### Parameters

[`Parameters`](/src/interactive_pipe/data_objects/parameters.py) class is used to store/reload dictionaries (usually pipeline parameters) to disk.
- Supports json & [yaml](https://pypi.org/project/PyYAML/) formats

### Image

[`Image`](/src/interactive_pipe/data_objects/image.py) class deals with loading/saving images from disk.

It uses whatever library is available to save images (among [PIL](https://pypi.org/project/Pillow/) by default & [cv2](https://pypi.org/project/opencv-python/))

- Internal data is stored using [numpy arrays](https://pypi.org/project/numpy/) and by default images are normalized in the [0, 1] range and stored as float32
- It has a `.show()` method, useful inside a jupyter notebook

### Curve

[`Curve`](/src/interactive_pipe/data_objects/curves.py) class deals with multiple 2D signals.

It can be used in a standalone fashion to reduce the amount of code you'd write every time you'd use matplotlib for 2D signal plots.

It uses matplotlib to display graphs inside an interactive pipe graphical window.
- It has a `.show()` method, useful inside a jupyter notebook

## Graphical Module

Currently supported backends:
- `qt` based on either PySide or PyQt depending on what you have
- `mpl` matplotlib used for scientific visualization
- `nb` based on [ipywidgets](https://ipywidgets.readthedocs.io/en/stable/) used in jupyter notebooks
- `gradio` web-based interface for sharing

### Backend Implementations

| Qt | Matplotlib | Jupyter | Component |
|:-----:|:------:|:----: |:---- |
| `InteractivePipeQT` | `InteractivePipeMatplotlib` | `InteractivePipeJupyter` | GUI Class name |
| [qt_gui.py](/src/interactive_pipe/graphical/qt_gui.py) | [mpl_gui.py](/src/interactive_pipe/graphical/mpl_gui.py) | [nb_gui.py](/src/interactive_pipe/graphical/nb_gui.py) | Code for GUI & Window |
| [qt_control.py](/src/interactive_pipe/graphical/qt_control.py) | [mpl_control.py](/src/interactive_pipe/graphical/mpl_control.py) | [nb_control.py](/src/interactive_pipe/graphical/nb_control.py) | Code for widget controls |

### InteractivePipeGUI

[`InteractivePipeGUI`](/src/interactive_pipe/graphical/gui.py) is the main app. 

- It adds an app with a GUI on top of a HeadlessPipeline. Widgets will update the pipeline parameters. 
- It stores the headless pipeline & the list of controls.
- It deals with key bindings (keyboard press triggers a function, function docstring is shown to the user when they press "F1" help)
- It deals with printing the help.
- A few special methods may be redefined for some specific backend needs: `reset_parameters`, `close`, `save_parameters`, `load_parameters`, `print_parameters`, `display_graph`, `help`
- Docstring of these methods will be used in the "F1" help descriptions
- Redefining `print_message` will allow a window popup for instance.

### InteractivePipeWindow

[`InteractivePipeWindow`](/src/interactive_pipe/graphical/window.py) is the window which displays the results & the sliders.

- `.size` = `(w, h)` / `fullscreen` / `maximized` defines the user expected window size
- It deals with the graphical refresh
- It allows refreshing the canvas (displaying two images side by side or four images in a 2x2 square fashion for instance)

## Testing

The project includes comprehensive test coverage:

- Core: `test_filter.py`, `test_core.py`, `test_engine.py`, `test_cache.py`
- Headless: `test_headless.py`, `test_controller.py`, `test_recorder.py`
- Data Objects: `test_image.py`, `test_curves.py`, `test_parameters.py`, `test_table.py`
- Decorators: `test_decorator.py`
- Context API: `test_context.py`, `test_context_compatibility.py`

## Contributing

If you want to contribute to interactive_pipe, please:

1. Check the architecture to understand where your changes fit
2. Run the test suite before and after your changes
3. Add tests for new features
4. Follow the existing code style
5. See the main README for development workflow
