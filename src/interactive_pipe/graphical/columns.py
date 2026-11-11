"""Spread the controls below the images over several columns (pure Python).

Shared by the Qt and Dear PyGui backends: the controls keep their order and
are cut into contiguous columns of balanced heights. The window uses the
fewest columns that let the controls fit the height left by the images, as
many as the width allows; the controls scroll only when even that is not
enough.
"""

from typing import List, Sequence

__all__ = ["split_into_columns", "columns_height", "columns_width", "choose_column_count"]


def _fits(heights: Sequence[float], count: int, spacing: float, cap: float) -> bool:
    used, column = 1, 0.0
    for height in heights:
        needed = height if column == 0.0 else column + spacing + height
        if needed <= cap or column == 0.0:
            column = needed
        else:
            used, column = used + 1, height
            if used > count:
                return False
    return True


def split_into_columns(heights: Sequence[float], count: int, spacing: float = 0.0) -> List[List[int]]:
    """Indices of the rows of each column: contiguous runs, in order, the
    tallest column as short as possible. Returns at most `count` columns
    (fewer when that is as short), none of them empty."""
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    if not heights:
        return []
    count = min(count, len(heights))
    # smallest cap such that the greedy fill uses <= count columns
    low = max(heights)
    high = sum(heights) + spacing * (len(heights) - 1)
    for _ in range(60):
        if high - low < 0.5:
            break
        middle = (low + high) / 2.0
        if _fits(heights, count, spacing, middle):
            high = middle
        else:
            low = middle
    columns: List[List[int]] = [[]]
    column = 0.0
    for index, height in enumerate(heights):
        needed = height if not columns[-1] else column + spacing + height
        if columns[-1] and needed > high:
            columns.append([index])
            column = height
        else:
            columns[-1].append(index)
            column = needed
    return columns


def columns_height(heights: Sequence[float], count: int, spacing: float = 0.0) -> float:
    """Height of the tallest column when spreading the rows over `count` columns."""
    return max(
        (
            sum(heights[i] for i in column) + spacing * (len(column) - 1)
            for column in split_into_columns(heights, count, spacing)
        ),
        default=0.0,
    )


def columns_width(widths: Sequence[float], columns: Sequence[Sequence[int]], column_gap: float = 0.0) -> float:
    """Width of `columns` side by side: each one as wide as its widest row."""
    if not columns:
        return 0.0
    return sum(max(widths[i] for i in column) for column in columns) + column_gap * (len(columns) - 1)


def choose_column_count(
    heights: Sequence[float],
    widths: Sequence[float],
    width_room: float,
    height_room: float,
    spacing: float = 0.0,
    column_gap: float = 0.0,
) -> int:
    """Fewest columns whose tallest one fits `height_room`, limited to what
    `width_room` holds (each column as wide as its widest row, `column_gap`
    apart). When even the most columns do not fit, the most columns (the
    controls scroll)."""
    if len(widths) != len(heights):
        raise ValueError(f"{len(heights)} heights but {len(widths)} widths")
    best = 1
    for count in range(1, len(heights) + 1):
        columns = split_into_columns(heights, count, spacing)
        if count > 1 and columns_width(widths, columns, column_gap) > width_room:
            break
        best = count
        if columns_height(heights, count, spacing) <= height_room:
            break
    return best
