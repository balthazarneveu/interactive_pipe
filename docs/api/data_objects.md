# Data Objects

Data objects are specialized containers for images, curves, and tables that provide automatic visualization and I/O capabilities. When returned from filters, they are automatically displayed by the GUI.

## Image

::: interactive_pipe.data_objects.image.Image

The `Image` class wraps numpy arrays representing images (H x W x 3, normalized to [0, 1]). It provides convenient load/save operations with multiple backends.

### Basic Usage

```python
from interactive_pipe import Image
import numpy as np

# Create from numpy array
img_array = np.random.rand(256, 256, 3)  # [0, 1] range
img = Image(img_array, title="Random Image")

# Create from file
img = Image.from_file("photo.jpg")

# Access the numpy array
array = img.data
print(array.shape)  # (height, width, 3)

# Save to file
img.save("output.png")

# Display with matplotlib
img.show()
```

### Loading Images

```python
from interactive_pipe import Image

# Load with PIL backend (default)
img = Image.from_file("photo.jpg", backend="pillow")

# Load with OpenCV backend
img = Image.from_file("photo.jpg", backend="opencv")

# Load with custom title
img = Image.from_file("photo.jpg", title="My Photo")
```

### Saving Images

```python
# Save as PNG (8-bit)
img.save("output.png")

# Save as JPEG
img.save("output.jpg")

# Save as TIFF
img.save("output.tif")

# Specify backend
img.save("output.png", backend="opencv")

# 16-bit precision (OpenCV only)
img.save("output.tif", backend="opencv", precision=16)
```

### Image Backends

Two backends are available:

- **`pillow`** (default) - PIL/Pillow library
  - Supports: PNG, JPEG, most common formats
  - Precision: 8-bit only
  
- **`opencv`** - OpenCV library
  - Supports: PNG, JPEG, TIFF, and more
  - Precision: 8-bit or 16-bit

### Using in Filters

Images are automatically displayed when returned from filters:

```python
from interactive_pipe import interactive, Image
import numpy as np

@interactive(brightness=(0.5, [0.0, 1.0]))
def adjust_brightness(img_array, brightness=0.5):
    """Filter receives numpy array, can return Image object."""
    result = img_array * brightness
    
    # Wrap in Image for custom title
    return Image(result, title=f"Brightness: {brightness:.2f}")
```

You can also return plain numpy arrays - they will be displayed as images automatically:

```python
@interactive(brightness=(0.5, [0.0, 1.0]))
def adjust_brightness(img_array, brightness=0.5):
    """Return plain numpy array - works too!"""
    return img_array * brightness
```

### Properties

```python
img = Image(array, title="My Image")

# Access data
img.data          # numpy array (H x W x 3)
img.title         # "My Image"
img.path          # Path object (if loaded from file)
```

## Curve

::: interactive_pipe.data_objects.curves.Curve

The `Curve` class represents multiple 2D curves for plotting. It's useful for displaying line plots, histograms, and other 2D data visualizations.

### Basic Usage

```python
from interactive_pipe import Curve, SingleCurve
import numpy as np

# Create curves
x = np.linspace(0, 10, 100)
y1 = np.sin(x)
y2 = np.cos(x)

curve1 = SingleCurve(x, y1, label="sin(x)", style="r-")
curve2 = SingleCurve(x, y2, label="cos(x)", style="b--")

# Combine into Curve object
curves = Curve(
    [curve1, curve2],
    xlabel="Time (s)",
    ylabel="Amplitude",
    title="Trigonometric Functions",
    grid=True
)

# Display
curves.show()

# Save as image
curves.save("plot.png")
```

### Creating from Different Formats

```python
import numpy as np
from interactive_pipe import Curve

x = np.linspace(0, 10, 100)
y1 = np.sin(x)
y2 = np.cos(x)

# List of tuples: (x, y, style, label)
curves = Curve([
    (x, y1, "r-", "sin(x)"),
    (x, y2, "b--", "cos(x)")
])

# List of dicts
curves = Curve([
    {"x": x, "y": y1, "label": "sin(x)", "style": "r-"},
    {"x": x, "y": y2, "label": "cos(x)", "style": "b--"}
])

# Just y values (x auto-generated)
curves = Curve([y1, y2])

# Single numpy array
curves = Curve(y1)
```

### Properties and Methods

```python
# Access properties
curves.curves     # List of SingleCurve objects
curves.xlabel     # X-axis label
curves.ylabel     # Y-axis label
curves.title      # Plot title
curves.grid       # Grid enabled/disabled
curves.xlim       # X-axis limits (tuple)
curves.ylim       # Y-axis limits (tuple)

# Access individual curves (indexing)
first_curve = curves[0]        # SingleCurve
first_three = curves[0:3]      # List of SingleCurve

# Modify curves
curves[0] = new_curve
curves.append(another_curve)
curves.prepend(intro_curve)

# Set properties
curves.xlabel = "New X Label"
curves.title = "Updated Title"
curves.grid = True
curves.xlim = (0, 5)
curves.ylim = (-1, 1)
```

### Using in Filters

```python
from interactive_pipe import interactive, Curve
import numpy as np

@interactive(frequency=(1.0, [0.1, 5.0]))
def generate_waveform(img, frequency=1.0):
    """Generate and display waveform."""
    x = np.linspace(0, 10, 1000)
    y = np.sin(2 * np.pi * frequency * x)
    
    curve = Curve(
        [(x, y, "b-")],
        xlabel="Time (s)",
        ylabel="Amplitude",
        title=f"Sine Wave ({frequency:.1f} Hz)",
        grid=True
    )
    
    return [img, curve]  # Return both image and curve
```

### Saving and Loading

```python
# Save as image
curve.save("plot.png")
curve.save("plot.jpg")

# Save as pickle (preserves all data)
curve.save("data.pkl")

# Load from pickle
curve = Curve.from_file("data.pkl")
```

## SingleCurve

::: interactive_pipe.data_objects.curves.SingleCurve

The `SingleCurve` class represents a single 2D curve defined by x and y arrays. It's typically used as a building block for `Curve` objects.

### Basic Usage

```python
from interactive_pipe import SingleCurve
import numpy as np

# Create curve
x = np.linspace(0, 10, 100)
y = np.sin(x)

curve = SingleCurve(
    x=x,
    y=y,
    label="sin(x)",
    style="r-",
    linewidth=2,
    markersize=5,
    alpha=0.8
)

# Access properties
curve.x         # numpy array
curve.y         # numpy array
curve.label     # "sin(x)"
curve.style     # "r-"
curve.alpha     # 0.8
```

### Style Parameters

```python
curve = SingleCurve(
    x, y,
    style="ro-",        # Matplotlib format string: r=red, o=circles, -=line
    label="My Curve",   # Legend label
    linestyle="--",     # Line style: "-", "--", "-.", ":"
    linewidth=2,        # Line width in points
    markersize=8,       # Marker size in points
    alpha=0.7           # Transparency (0.0 to 1.0)
)
```

### Saving and Loading

```python
# Save as CSV (x, y columns only)
curve.save("data.csv")

# Save as pickle (preserves all properties)
curve.save("data.pkl")

# Load from CSV
curve = SingleCurve.from_file("data.csv", label="Loaded Data", style="b-")

# Load from pickle
curve = SingleCurve.from_file("data.pkl")

# Convert to pandas DataFrame (if pandas installed)
df = curve.as_dataframe()
```

### Properties

All properties can be read and modified:

```python
curve.x = new_x_array
curve.y = new_y_array
curve.label = "New Label"
curve.style = "b--"
curve.alpha = 0.5
```

## Table

::: interactive_pipe.data_objects.table.Table

The `Table` class displays tabular data in the GUI. It works with or without pandas, though pandas enables additional features like CSV export.

### Basic Usage

```python
from interactive_pipe import Table

# From dict of lists (column-oriented)
table = Table({
    "Name": ["Alice", "Bob", "Charlie"],
    "Age": [25, 30, 35],
    "Score": [92.5, 87.3, 95.1]
})

# From list of dicts (row-oriented)
table = Table([
    {"Name": "Alice", "Age": 25, "Score": 92.5},
    {"Name": "Bob", "Age": 30, "Score": 87.3},
    {"Name": "Charlie", "Age": 35, "Score": 95.1}
])

# With title and custom precision
table = Table(
    data,
    title="Test Results",
    precision=3  # 3 decimal places for floats
)
```

### Creating from Numpy Array

```python
import numpy as np
from interactive_pipe import Table

# 2D numpy array with column names
data = np.array([
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9]
])

table = Table(
    data,
    columns=["A", "B", "C"],
    title="Matrix Data"
)

# Headerless table (for raw matrices)
table = Table(
    data,
    columns=None,  # No headers
    title="Raw Matrix"
)
```

### Creating from Pandas DataFrame

```python
import pandas as pd
from interactive_pipe import Table

# From DataFrame (requires pandas)
df = pd.DataFrame({
    "X": [1, 2, 3],
    "Y": [4, 5, 6]
})

table = Table(df, title="From DataFrame")
```

### Using in Filters

```python
from interactive_pipe import interactive, Table
import numpy as np

@interactive(threshold=(0.5, [0.0, 1.0]))
def analyze_image(img, threshold=0.5):
    """Compute statistics and display as table."""
    # Compute statistics
    mean_val = float(img.mean())
    std_val = float(img.std())
    min_val = float(img.min())
    max_val = float(img.max())
    
    # Create table
    stats = Table(
        {
            "Metric": ["Mean", "Std Dev", "Min", "Max"],
            "Value": [mean_val, std_val, min_val, max_val]
        },
        title="Image Statistics",
        precision=4
    )
    
    return [img, stats]
```

### Properties

```python
table = Table(data)

# Access properties
table.columns    # List of column names
table.values     # List of lists (row-major)
table.title      # Optional title string
table.precision  # Float formatting precision

# Modify properties
table.title = "New Title"
table.precision = 3
table.columns = ["Col1", "Col2", "Col3"]
```

### Indexing and Iteration

```python
# Get number of rows
num_rows = len(table)

# Iterate over rows (as dicts)
for row in table:
    print(row)  # {"Name": "Alice", "Age": 25, ...}

# Access by row index
row = table[0]        # First row as dict
row = table[-1]       # Last row as dict

# Access by column name
ages = table["Age"]   # List of all ages

# Slice rows
rows = table[0:2]     # First two rows as list of dicts
```

### Saving and Loading

```python
# Save as pickle
table.save("data.pkl")

# Save as CSV (requires pandas)
table.save("data.csv")

# Load from pickle
table = Table.from_file("data.pkl")

# Load from CSV (requires pandas)
table = Table.from_file("data.csv", title="Loaded Data")

# Convert to pandas DataFrame (requires pandas)
df = table.as_dataframe()
```

### Pandas Support

Tables work without pandas, but pandas enables additional features:

| Feature | Without Pandas | With Pandas |
|---------|---------------|-------------|
| Basic display | ✅ | ✅ |
| Dict/list input | ✅ | ✅ |
| Numpy array input | ✅ | ✅ |
| DataFrame input | ❌ | ✅ |
| CSV export | ❌ | ✅ |
| CSV import | ❌ | ✅ |
| `.as_dataframe()` | ❌ | ✅ |

To enable pandas features:

```bash
pip install pandas
```

## Complete Example

Here's a comprehensive example using all data objects:

```python
from interactive_pipe import (
    interactive,
    interactive_pipeline,
    Image,
    Curve,
    SingleCurve,
    Table,
    layout
)
import numpy as np

def apply_blur(img_array, blur_sigma):
    """Simple box blur implementation."""
    if blur_sigma <= 0:
        return img_array

    # Convert sigma to integer radius
    radius = int(blur_sigma)
    if radius == 0:
        return img_array

    h, w, c = img_array.shape
    blurred = img_array.copy()

    # Apply horizontal blur
    for y in range(h):
        for x in range(w):
            x_start = max(0, x - radius)
            x_end = min(w, x + radius + 1)
            blurred[y, x] = img_array[y, x_start:x_end].mean(axis=0)

    # Apply vertical blur
    for y in range(h):
        for x in range(w):
            y_start = max(0, y - radius)
            y_end = min(h, y + radius + 1)
            blurred[y, x] = blurred[y_start:y_end, x].mean(axis=0)

    return blurred

@interactive(blur=(0.0, [0.0, 10.0]))
def process_and_analyze(img_array, blur=0.0):
    """Process image and return multiple visualizations."""

    # Process image
    processed = apply_blur(img_array, blur)


    # Compute histogram
    hist, bins = np.histogram(processed.ravel(), bins=50, range=(0, 1))
    bin_centers = (bins[:-1] + bins[1:]) / 2

    # Create curve
    histogram_curve = Curve(
        [(bin_centers, hist, "b-")],
        xlabel="Pixel Value",
        ylabel="Frequency",
        title="Histogram",
        grid=True
    )

    # Compute statistics
    stats_table = Table(
        {
            "Metric": ["Mean", "Std", "Min", "Max"],
            "Original": [
                img_array.mean(),
                img_array.std(),
                img_array.min(),
                img_array.max()
            ],
            "Processed": [
                processed.mean(),
                processed.std(),
                processed.min(),
                processed.max()
            ]
        },
        title="Statistics Comparison",
        precision=4
    )

    # Set custom layout
    layout.grid([
        ["original_img", "processed_img"],
        ["histogram_curve", "stats_table"]
    ])

    return processed, histogram_curve, stats_table

@interactive_pipeline(gui='qt', name="Image Analysis")
def analysis_pipeline(original_img):
    processed_img, histogram_curve, stats_table = process_and_analyze(original_img)
    return [original_img, processed_img, histogram_curve, stats_table]

# Launch
if __name__ == "__main__":
    test_img = np.random.rand(256, 256, 3)
    analysis_pipeline(test_img)
```

## See Also

- [Decorators](decorators.md) - Using data objects in filters
- [Context API](context.md) - Controlling display with `layout`
- [User Guide](../guide/filters.md) - Tutorials and examples
