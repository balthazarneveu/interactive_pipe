# Tables

Return a `Table` to display tabular data — handy for live statistics next to the image being processed. Tables render on all four backends.

```python
from interactive_pipe import Table, interactive

@interactive()
def compute_statistics(img) -> Table:
    channels = ["Red", "Green", "Blue"]
    stats = {
        "Channel": channels,
        "Mean": [img[:, :, i].mean() for i in range(3)],
        "Std": [img[:, :, i].std() for i in range(3)],
    }
    return Table(stats, title="Image statistics", precision=4)
```

## Accepted input shapes

- a dict of columns: `{"Channel": [...], "Mean": [...]}` (as above)
- a 2D numpy array plus `columns=["X", "Y", ...]`
- a numpy array with `columns=None` for a headerless raw matrix
- a list of row dicts: `[{"x": 1, "y": 2}, ...]`
- a pandas `DataFrame` (when pandas is installed; pandas is optional)

`precision` controls float formatting. `table.as_dataframe()` converts back to pandas, and tables save to `.csv` / `.pkl` via `.save(path)`.

Full example: [demo/table_demo.py](https://github.com/balthazarneveu/interactive_pipe/blob/master/demo/table_demo.py) (statistics, coordinate grids, DataFrames side by side).

## API

Constructor details: [`Table`](../api/data-objects.md).
