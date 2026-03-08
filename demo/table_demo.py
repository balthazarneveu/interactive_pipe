"""
Demo showcasing Table data type with various table examples.

This demo demonstrates:
- Table visualization with adjustable parameters
- Image generation/processing with adjustable parameters
- Computing statistics from image data and displaying in tabular format
- Numpy grid/array tables
- Multiplication tables
- Coordinate grids
- List of dictionaries tables
- Pandas DataFrame tables
- Multiple table types side-by-side
"""

import argparse

import numpy as np

from interactive_pipe import interactive, interactive_pipeline, layout
from interactive_pipe.data_objects.table import Table

# Try to import pandas, but make it optional
try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


@interactive(
    noise_level=(0.1, [0.0, 0.5]),  # Float slider for noise level
    brightness=(0.5, [0.0, 1.0]),  # Float slider for brightness
    image_size=(200, [100, 400]),  # Int slider for image size
)
def generate_noisy_image(noise_level: float = 0.1, brightness: float = 0.5, image_size: int = 200):
    """Generate a test image with adjustable noise and brightness."""
    img = np.ones((image_size, image_size, 3)) * brightness
    img += np.random.randn(*img.shape) * noise_level
    return np.clip(img, 0, 1)


@interactive()
def compute_statistics(img):
    """Compute per-channel statistics and return as Table."""
    channels = ["Red", "Green", "Blue"]
    stats = {
        "Channel": channels,
        "Mean": [f"{img[:, :, i].mean():.4f}" for i in range(3)],
        "Std": [f"{img[:, :, i].std():.4f}" for i in range(3)],
        "Min": [f"{img[:, :, i].min():.4f}" for i in range(3)],
        "Max": [f"{img[:, :, i].max():.4f}" for i in range(3)],
    }
    table = Table(stats, title="Image Statistics", precision=4)

    layout.set_style("stats", title="Channel Statistics")

    return table


@interactive(
    grid_size=(5, [3, 10]),  # Size of the grid
)
def create_coordinate_grid(grid_size: int = 5):
    """Create a coordinate grid table from numpy array."""
    # Create a grid of (x, y) coordinates
    x_coords = np.arange(grid_size).repeat(grid_size)
    y_coords = np.tile(np.arange(grid_size), grid_size)
    distances = np.sqrt(x_coords**2 + y_coords**2)
    angles = np.arctan2(y_coords, x_coords) * 180 / np.pi

    # Create 2D numpy array
    grid_data = np.column_stack([x_coords, y_coords, distances, angles])
    columns = ["X", "Y", "Distance", "Angle (deg)"]

    table = Table(grid_data, columns=columns, title="Coordinate Grid", precision=2)
    layout.set_style("grid", title="Coordinate Grid Table")

    return table


@interactive(
    table_size=(10, [5, 20]),  # Size of multiplication table
)
def create_multiplication_table(table_size: int = 10):
    """Create a multiplication table from numpy array."""
    # Create multiplication table as numpy grid
    rows = np.arange(1, table_size + 1).reshape(-1, 1)
    cols = np.arange(1, table_size + 1).reshape(1, -1)
    mult_grid = rows * cols

    # Add row and column headers by creating a larger array
    # First column: row numbers, remaining columns: multiplication results
    table_data = np.column_stack([np.arange(1, table_size + 1), mult_grid])
    columns = ["×"] + [str(i) for i in range(1, table_size + 1)]

    table = Table(table_data, columns=columns, title="Multiplication Table", precision=0)
    layout.set_style("mult", title="Multiplication Table")

    return table


@interactive(
    matrix_size=(4, [3, 8]),  # Size of transformation matrix demo
)
def create_transformation_matrix(matrix_size: int = 4):
    """Create a transformation matrix example from numpy array."""
    # Create a rotation/scaling matrix example
    angle = np.pi / 4
    scale = 1.5
    rotation_matrix = np.array(
        [
            [scale * np.cos(angle), -scale * np.sin(angle)],
            [scale * np.sin(angle), scale * np.cos(angle)],
        ]
    )

    # Create input/output pairs
    inputs = np.random.randn(matrix_size, 2) * 2
    outputs = (rotation_matrix @ inputs.T).T

    # Combine into table
    table_data = np.column_stack(
        [
            inputs[:, 0],
            inputs[:, 1],
            outputs[:, 0],
            outputs[:, 1],
            np.linalg.norm(outputs, axis=1) - np.linalg.norm(inputs, axis=1),
        ]
    )
    columns = ["Input X", "Input Y", "Output X", "Output Y", "Scale Change"]

    table = Table(table_data, columns=columns, title="Transformation Matrix Demo", precision=3)
    layout.set_style("transform", title="Matrix Transformation")

    return table


@interactive(
    num_entries=(8, [5, 15]),  # Number of entries in the list
)
def create_list_of_dicts_table(num_entries: int = 8):
    """Create a table from a list of dictionaries."""
    # Simulate some data records
    records = []
    for i in range(num_entries):
        records.append(
            {
                "ID": i + 1,
                "Name": f"Item_{i + 1}",
                "Value": np.random.rand() * 100,
                "Category": np.random.choice(["A", "B", "C"]),
                "Active": np.random.choice([True, False]),
            }
        )

    table = Table(records, title="List of Dictionaries Example", precision=2)
    layout.set_style("records", title="Data Records")

    return table


@interactive(
    num_samples=(10, [5, 20]),  # Number of data samples
    show_aggregated=(True,),  # Whether to show aggregated statistics
)
def create_pandas_table(num_samples: int = 10, show_aggregated: bool = True):
    """Create a table from a pandas DataFrame with data analysis."""
    if not PANDAS_AVAILABLE:
        # Fallback: create a simple table explaining pandas is needed
        fallback_data = {
            "Note": ["Pandas not available"],
            "Install": ["pip install pandas"],
        }
        table = Table(fallback_data, title="Pandas Example (Not Available)", precision=0)
        layout.set_style("pandas", title="Pandas DataFrame Example")
        return table

    # Create sample data with pandas
    dates = pd.date_range("2024-01-01", periods=num_samples, freq="D")
    df = pd.DataFrame(
        {
            "Date": dates,
            "Sales": np.random.rand(num_samples) * 1000 + 500,
            "Quantity": np.random.randint(10, 100, num_samples),
            "Region": np.random.choice(["North", "South", "East", "West"], num_samples),
            "Discount": np.random.rand(num_samples) * 0.3,
        }
    )

    # Add calculated columns
    df["Revenue"] = df["Sales"] * df["Quantity"] * (1 - df["Discount"])
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    if show_aggregated:
        # Add summary statistics as additional rows
        summary_rows = pd.DataFrame(
            {
                "Date": ["---", "---", "---", "---"],
                "Sales": [
                    df["Sales"].sum(),
                    df["Sales"].mean(),
                    df["Sales"].min(),
                    df["Sales"].max(),
                ],
                "Quantity": [
                    df["Quantity"].sum(),
                    df["Quantity"].mean(),
                    df["Quantity"].min(),
                    df["Quantity"].max(),
                ],
                "Region": ["TOTAL", "AVG", "MIN", "MAX"],
                "Discount": [
                    df["Discount"].sum(),
                    df["Discount"].mean(),
                    df["Discount"].min(),
                    df["Discount"].max(),
                ],
                "Revenue": [
                    df["Revenue"].sum(),
                    df["Revenue"].mean(),
                    df["Revenue"].min(),
                    df["Revenue"].max(),
                ],
            }
        )
        # Combine original data with summary
        combined_df = pd.concat([df, summary_rows], ignore_index=True)
        table = Table(combined_df, title="Pandas DataFrame with Aggregated Stats", precision=2)
    else:
        table = Table(df, title="Pandas DataFrame Example", precision=2)

    layout.set_style("pandas", title="Pandas DataFrame Table")

    return table


def table_pipeline():
    """Main pipeline function showcasing multiple table types."""
    img = generate_noisy_image()
    stats = compute_statistics(img)
    grid = create_coordinate_grid()
    mult_table = create_multiplication_table()
    transform_table = create_transformation_matrix()
    records_table = create_list_of_dicts_table()
    pandas_table = create_pandas_table()
    return [
        [img, stats, grid],
        [mult_table, transform_table, records_table, pandas_table],
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Table demo with image statistics")
    parser.add_argument(
        "-b",
        "--backend",
        type=str,
        choices=["qt", "gradio", "mpl", "nb", "dpg"],
        default="qt",
        help="Backend to use: qt, gradio, mpl, nb, or dpg (default: qt)",
    )
    args = parser.parse_args()

    interactive_pipeline(gui=args.backend, cache=False, name="Table Demo")(table_pipeline)()
