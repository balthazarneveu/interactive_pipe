import pytest

try:
    from interactive_pipe.core import FilterCore
except:
    import helper
    from core import FilterCore


class MultiplyFilter(FilterCore):
    def apply(self, img, scalar):
        return [[value * scalar for value in row] for row in img]


def test_filter_apply():
    filter = MultiplyFilter("multiply", default_params=[1.])
    img = [[1, 2, 3], [4, 5, 6]]
    result = filter.apply(img, 2)
    assert result == [[2, 4, 6], [8, 10, 12]]


def test_filter_reset_cache():
    filter = MultiplyFilter()
    filter.cache_mem.result = [[2, 4, 6], [8, 10, 12]]
    filter.reset_cache()
    assert filter.cache_mem.result is None
    assert filter.cache_mem.name == 'MultiplyFilter'
