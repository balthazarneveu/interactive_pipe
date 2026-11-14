"""A list returned by a filter is one value when the pipeline line assigns one name.

Reproducer of the dogfooding log (item 2): `dets = make()` received a list for
2+ items, raised for 0 items and silently received the item itself for 1.
"""

import pytest

from interactive_pipe import interactive
from interactive_pipe.core.engine import FilterError
from interactive_pipe.core.filter import FilterOutputError
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(n=(1, [0, 5]))
def lo_make(n=1):
    return [dict(a=i) for i in range(n)]


@interactive()
def lo_show(dets):
    return f"{type(dets).__name__} of {len(dets)}"


def lo_pipeline():
    dets = lo_make()
    txt = lo_show(dets)
    return txt


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_one_name_receives_the_list(n):
    pipe = HeadlessPipeline.from_function(lo_pipeline, inputs=[])
    assert pipe(n=n) == (f"list of {n}",)


@interactive()
def lo_pair():
    return [1.0, 2.0]


def test_several_names_still_unpack_a_list():
    def pipeline():
        a, b = lo_pair()
        return a, b

    assert HeadlessPipeline.from_function(pipeline, inputs=[])() == (1.0, 2.0)

    def too_many():
        a, b, c = lo_pair()
        return a

    with pytest.raises(FilterError, match="returned 2 value"):
        HeadlessPipeline.from_function(too_many, inputs=[])()


@interactive()
def lo_tuple():
    return 1.0, 2.0


@interactive()
def lo_one_tuple():
    return (3.0,)


def test_tuples_keep_their_rule():
    def one_name():
        x = lo_tuple()
        return x

    with pytest.raises(FilterError, match=r"returned 2 values but the pipeline assigns 1 name") as info:
        HeadlessPipeline.from_function(one_name, inputs=[])()
    assert "return (values,)" in str(info.value) and "as a list" in str(info.value)
    assert isinstance(info.value.__cause__, FilterOutputError) or "FilterOutputError" in str(info.value)

    def one_tuple():
        x = lo_one_tuple()
        return x

    assert HeadlessPipeline.from_function(one_tuple, inputs=[])() == (3.0,)  # (value,) is still the value
