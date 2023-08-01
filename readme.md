# Concept
- Develop your algorithm while debugging with plots, while checking robustness & continuity to parameters change
- Tune your algo and save your parameters for later batch processing
- Ready to batch under the hood, the processing engine can be ran without GUI (therefore allowing to use the same code for tuning & batch processing if needed).


# Core class

Very simple filter defined from a specific function
```python
PureFilter(apply_fn: Callable, default_params = {"param_1": 10, ...}, name=Optional)
```


```python
def mad(img , coeff=1, bias=0):
    mad_res = img*coeff+bias
    return [mad_res]
PureFilter(apply_fn=mad, default_params={"coeff": 1, "bias": 0})
```
Note that `default_params` is  optional here - if not provided, the keyword args of the `mad` function will simply be used.

:warning: Warning - requires extra care regarding typos for `default_params`

This pain point is one of the motivation for using AutoFilter


```python
def mad(
    img: np.numpy,
    coeff=Slider(1, 0, 10, "coefficient"),
    bias=Slider(0, -10, 10, "bias"),
):
    mad_res = img*coeff+bias
    return [mad_res]
AutoFilter(apply_fn=mad)
```