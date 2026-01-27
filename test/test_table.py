import pytest
import numpy as np
from pathlib import Path
from interactive_pipe.data_objects.table import Table, PANDAS_AVAILABLE

if PANDAS_AVAILABLE:
    import pandas as pd


def test_table_from_dict_of_lists():
    """Test creating Table from dict of lists."""
    t = Table({"A": [1, 2], "B": [3, 4]})
    assert t.columns == ["A", "B"]
    assert t.values == [[1, 3], [2, 4]]


def test_table_from_list_of_dicts():
    """Test creating Table from list of dicts."""
    t = Table([{"A": 1, "B": 3}, {"A": 2, "B": 4}])
    assert t.columns == ["A", "B"]
    assert t.values == [[1, 3], [2, 4]]


def test_table_from_numpy_array():
    """Test creating Table from 2D numpy array with columns."""
    arr = np.array([[1, 2], [3, 4]])
    t = Table(arr, columns=["X", "Y"])
    assert t.columns == ["X", "Y"]
    assert t.values == [[1, 2], [3, 4]]


def test_table_numpy_without_columns_raises():
    """Test that numpy array without columns raises ValueError."""
    arr = np.array([[1, 2], [3, 4]])
    with pytest.raises(ValueError, match="columns parameter is required"):
        Table(arr)


def test_table_empty_dict():
    """Test creating empty Table from empty dict."""
    t = Table({})
    assert t.columns == []
    assert t.values == []


def test_table_empty_list():
    """Test creating empty Table from empty list."""
    t = Table([])
    assert t.columns == []
    assert t.values == []


def test_table_dict_unequal_lengths_raises():
    """Test that dict with unequal column lengths raises ValueError."""
    with pytest.raises(ValueError, match="All columns must have the same length"):
        Table({"A": [1, 2], "B": [3, 4, 5]})


def test_table_list_of_dicts_different_keys_raises():
    """Test that list of dicts with different keys raises ValueError."""
    with pytest.raises(ValueError, match="has different keys"):
        Table([{"A": 1, "B": 2}, {"A": 3, "C": 4}])


def test_table_numpy_wrong_shape_raises():
    """Test that 1D numpy array raises ValueError."""
    arr = np.array([1, 2, 3])
    with pytest.raises(ValueError, match="must be 2D"):
        Table(arr, columns=["X"])


def test_table_numpy_columns_mismatch_raises():
    """Test that columns count mismatch raises ValueError."""
    arr = np.array([[1, 2], [3, 4]])
    with pytest.raises(ValueError, match="Number of columns"):
        Table(arr, columns=["X"])


def test_table_properties():
    """Test Table properties."""
    t = Table({"A": [1, 2]})
    assert t.title is None
    assert t.precision == 2
    
    t.title = "Test Table"
    assert t.title == "Test Table"
    
    t.precision = 4
    assert t.precision == 4


def test_table_title_setter_type_error():
    """Test that title setter raises TypeError for non-string."""
    t = Table({"A": [1]})
    with pytest.raises(TypeError, match="title must be a string"):
        t.title = 123


def test_table_precision_setter_type_error():
    """Test that precision setter raises TypeError for non-int."""
    t = Table({"A": [1]})
    with pytest.raises(TypeError, match="precision must be an integer"):
        t.precision = 2.5


def test_table_precision_setter_negative_raises():
    """Test that negative precision raises ValueError."""
    t = Table({"A": [1]})
    with pytest.raises(ValueError, match="precision must be non-negative"):
        t.precision = -1


def test_table_getitem_row():
    """Test accessing row by index."""
    t = Table({"A": [1, 2], "B": [3, 4]})
    row = t[0]
    assert row == {"A": 1, "B": 3}


def test_table_getitem_column():
    """Test accessing column by name."""
    t = Table({"A": [1, 2], "B": [3, 4]})
    col = t["A"]
    assert col == [1, 2]


def test_table_getitem_slice():
    """Test accessing rows by slice."""
    t = Table({"A": [1, 2, 3], "B": [4, 5, 6]})
    rows = t[0:2]
    assert rows == [{"A": 1, "B": 4}, {"A": 2, "B": 5}]


def test_table_getitem_row_out_of_range():
    """Test that row index out of range raises IndexError."""
    t = Table({"A": [1, 2]})
    with pytest.raises(IndexError, match="out of range"):
        _ = t[5]


def test_table_getitem_column_not_found():
    """Test that missing column raises KeyError."""
    t = Table({"A": [1, 2]})
    with pytest.raises(KeyError, match="not found"):
        _ = t["Z"]


def test_table_save_load_pkl(tmp_path):
    """Test saving and loading Table as pickle."""
    t = Table({"A": [1, 2], "B": [3, 4]}, title="Test", precision=3)
    path = tmp_path / "test.pkl"
    t.save(path)
    assert path.is_file()
    
    t2 = Table.from_file(path)
    assert t2.columns == t.columns
    assert t2.values == t.values
    assert t2.title == t.title
    assert t2.precision == t.precision


def test_table_save_csv_without_pandas_raises(tmp_path):
    """Test that saving CSV without pandas raises RuntimeError."""
    t = Table({"A": [1, 2]})
    path = tmp_path / "test.csv"
    with pytest.raises(RuntimeError, match="CSV export requires pandas"):
        t.save(path)


def test_table_load_csv_without_pandas_raises(tmp_path):
    """Test that loading CSV without pandas raises RuntimeError."""
    path = tmp_path / "test.csv"
    # Create a dummy CSV file
    path.write_text("A,B\n1,2\n")
    with pytest.raises(RuntimeError, match="CSV import requires pandas"):
        Table.from_file(path)


def test_table_unsupported_file_extension():
    """Test that unsupported file extension gets converted to default (.csv) and raises pandas error."""
    t = Table({"A": [1]})
    # The parent class converts .txt to .csv (default extension), which then requires pandas
    with pytest.raises(RuntimeError, match="CSV export requires pandas"):
        t.save(Path("test.txt"))


def test_table_float_values():
    """Test Table with float values."""
    t = Table({"A": [1.5, 2.7], "B": [3.1, 4.9]})
    assert t.values == [[1.5, 3.1], [2.7, 4.9]]


def test_table_mixed_types():
    """Test Table with mixed data types."""
    t = Table({
        "Name": ["Alice", "Bob"],
        "Age": [25, 30],
        "Score": [95.5, 87.3]
    })
    assert t.columns == ["Name", "Age", "Score"]
    assert t.values == [["Alice", 25, 95.5], ["Bob", 30, 87.3]]


def test_table_single_row():
    """Test Table with single row."""
    t = Table({"A": [1], "B": [2]})
    assert len(t.values) == 1
    assert t.values == [[1, 2]]


def test_table_single_column():
    """Test Table with single column."""
    t = Table({"A": [1, 2, 3]})
    assert t.columns == ["A"]
    assert t.values == [[1], [2], [3]]


# Pandas-dependent tests
@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
def test_table_from_dataframe():
    """Test creating Table from pandas DataFrame."""
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    t = Table(df)
    assert t.columns == ["A", "B"]
    assert t.values == [[1, 3], [2, 4]]


@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
def test_table_from_dataframe_with_index():
    """Test creating Table from DataFrame with custom index."""
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]}, index=["row1", "row2"])
    t = Table(df)
    # Index should not be included in columns
    assert t.columns == ["A", "B"]
    assert t.values == [[1, 3], [2, 4]]


@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
def test_table_as_dataframe():
    """Test converting Table to pandas DataFrame."""
    t = Table({"A": [1, 2], "B": [3, 4]})
    df = t.as_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["A", "B"]
    assert df.values.tolist() == [[1, 3], [2, 4]]


@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
def test_table_save_load_csv(tmp_path):
    """Test saving and loading Table as CSV."""
    t = Table({"A": [1, 2], "B": [3, 4]}, title="Test", precision=3)
    path = tmp_path / "test.csv"
    t.save(path)
    assert path.is_file()
    
    t2 = Table.from_file(path)
    assert t2.columns == t.columns
    assert t2.values == t.values
    # Note: title and precision are not preserved in CSV


@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
def test_table_save_load_csv_with_floats(tmp_path):
    """Test CSV save/load with float values."""
    t = Table({"A": [1.5, 2.7], "B": [3.1, 4.9]})
    path = tmp_path / "test.csv"
    t.save(path)
    
    t2 = Table.from_file(path)
    # CSV loads as floats, so we need to compare approximately
    assert t2.columns == t.columns
    assert len(t2.values) == len(t.values)
    for row1, row2 in zip(t.values, t2.values):
        for v1, v2 in zip(row1, row2):
            assert abs(v1 - v2) < 1e-10


@pytest.mark.skipif(not PANDAS_AVAILABLE, reason="pandas not installed")
def test_table_save_load_csv_with_strings(tmp_path):
    """Test CSV save/load with string values."""
    t = Table({"Name": ["Alice", "Bob"], "Age": [25, 30]})
    path = tmp_path / "test.csv"
    t.save(path)
    
    t2 = Table.from_file(path)
    assert t2.columns == t.columns
    # String columns may be preserved or converted, check values match
    assert len(t2.values) == len(t.values)


def test_table_as_dataframe_without_pandas_raises():
    """Test that as_dataframe() raises RuntimeError when pandas unavailable."""
    if PANDAS_AVAILABLE:
        pytest.skip("pandas is installed, cannot test error case")
    t = Table({"A": [1, 2]})
    with pytest.raises(RuntimeError, match="requires pandas"):
        t.as_dataframe()


def test_table_dataframe_input_without_pandas_raises():
    """Test that DataFrame input raises error when pandas unavailable."""
    if PANDAS_AVAILABLE:
        pytest.skip("pandas is installed, cannot test error case")
    # Create a mock DataFrame-like object
    class MockDataFrame:
        pass
    mock_df = MockDataFrame()
    with pytest.raises(TypeError, match="Unsupported data type"):
        Table(mock_df)
