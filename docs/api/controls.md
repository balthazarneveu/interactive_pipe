# Controls & panels

::: interactive_pipe.Control

::: interactive_pipe.CircularControl

::: interactive_pipe.RangeControl

::: interactive_pipe.TextPrompt

::: interactive_pipe.TimeControl

::: interactive_pipe.KeyboardControl

::: interactive_pipe.Panel

## Controls from annotations

Under `@interactive`, a parameter's type hint can declare its control instead
of the decorator ([guide](../guide/controls.md#controls-from-type-annotations)):

| Annotation | Control |
|---|---|
| `Annotated[float, (min, max)]`, `Annotated[int, (min, max, step), "label", "group"]` | slider |
| `Annotated[Tuple[float, float], (min, max)]` | `RangeControl` (two handles) |
| `Annotated[bool, "label"]` | checkbox |
| `Annotated[str, ["a", "b"]]`, `Literal["a", "b"]` | dropdown |
| `Literal[3, 5]`, an `Enum` | dropdown of labels; the filter receives the value / member |
| `Annotated[T, Control(...)]` (any control class) | that control |

The default value comes from the signature (`= 1.0`). A plain `float` / `bool`
/ `str` hint, `Optional[...]` or a `None` default make no widget.
