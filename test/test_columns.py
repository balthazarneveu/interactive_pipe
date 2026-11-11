"""Spreading the controls over columns (pure Python, shared by Qt and Dear PyGui)."""

import pytest

from interactive_pipe.graphical.columns import choose_column_count, columns_height, columns_width, split_into_columns


def test_split_keeps_the_order_and_balances_the_heights():
    heights = [35, 43, 35, 35, 42, 118, 40, 35, 40, 118, 35, 43, 35, 43, 35, 40]
    columns = split_into_columns(heights, 2, spacing=1)
    assert [i for column in columns for i in column] == list(range(len(heights)))
    assert len(columns) == 2
    tallest = columns_height(heights, 2, spacing=1)
    assert tallest < (sum(heights) + 15) / 2 + max(heights)  # close to half
    # no contiguous split into 2 has a shorter tallest column
    best = min(max(sum(heights[:k]) + k - 1, sum(heights[k:]) + len(heights) - k - 1) for k in range(1, len(heights)))
    assert tallest == best


def test_split_edge_cases():
    assert split_into_columns([], 3) == []
    assert split_into_columns([10, 20], 5) == [[0], [1]]
    assert split_into_columns([10, 20, 30], 1) == [[0, 1, 2]]
    with pytest.raises(ValueError):
        split_into_columns([10], 0)


def test_choose_uses_the_fewest_columns_that_fit():
    heights, widths = [40] * 10, [400] * 10  # 400 tall in one column
    assert choose_column_count(heights, widths, width_room=2000, height_room=500) == 1
    assert choose_column_count(heights, widths, width_room=2000, height_room=250) == 2
    assert choose_column_count(heights, widths, width_room=2000, height_room=100) == 5  # 2 rows each


def test_choose_is_limited_by_the_width():
    heights, widths = [40] * 10, [400] * 10
    assert choose_column_count(heights, widths, width_room=850, height_room=100, column_gap=10) == 2
    assert choose_column_count(heights, widths, width_room=300, height_room=100) == 1
    assert choose_column_count([], [], width_room=2000, height_room=0) == 1
    with pytest.raises(ValueError):
        choose_column_count([40], [], width_room=2000, height_room=0)


def test_choose_measures_each_column_by_its_widest_row():
    heights = [40, 40, 40, 40]
    widths = [434, 424, 424, 424]  # one wide row: only the first column is 434 wide
    columns = split_into_columns(heights, 2)
    assert columns_width(widths, columns, column_gap=16) == 434 + 16 + 424
    assert choose_column_count(heights, widths, width_room=874, height_room=80, column_gap=16) == 2
