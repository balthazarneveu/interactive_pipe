from interactive_pipe.core.filter import FilterCore, PureFilter


class MultiplyFilter(FilterCore):
    def apply(self, img, scalar=8, add=5):
        return [[value * scalar + add for value in row] for row in img]


def test_pure_filter():
    def mult(img, context={}, scalar=8, add=5):
        return [[value * scalar + add for value in row] for row in img]
    filt = PureFilter(apply_fn=mult, name="multiplication",
                      default_params={"scalar": 2, "add": 0})
    img = [[1, 2, 3], [4, 5, 6]]
    result = filt.run(img)
    assert result == [[2, 4, 6], [8, 10, 12]]


def test_filter_run_dict():
    filter = MultiplyFilter(name="multiply", default_params={
                            "add": 0, "scalar": 2})
    img = [[1, 2, 3], [4, 5, 6]]
    result = filter.run(img)
    assert result == [[2, 4, 6], [8, 10, 12]]


def test_filter_run_dict_missing_keys():
    filter = MultiplyFilter(name="multiply", default_params={"add": 0})
    img = [[1, 2, 3], [4, 5, 6]]
    result = filter.run(img)
    assert result == [[1*8, 2*8, 3*8], [4*8, 5*8, 6*8]]


def test_filter_apply():
    filter = MultiplyFilter(name="multiply", default_params={
                            "add": 0, "scalar": 1})
    img = [[1, 2, 3], [4, 5, 6]]
    result = filter.apply(img, scalar=2)
    assert result == [[5+2, 5+4, 5+6], [5+8, 5+10, 5+12]]


def test_filter_reset_cache():
    filter = MultiplyFilter()
    filter.cache_mem.result = [[2, 4, 6], [8, 10, 12]]
    filter.reset_cache()
    assert filter.cache_mem.result is None
    assert filter.cache_mem.name == 'MultiplyFilter'
