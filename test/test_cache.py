from interactive_pipe.core.cache import StateChange


def test_initial_state():
    sc = StateChange(name='Sample_Filter')
    assert sc.name == 'Sample_Filter'
    assert sc._stored_params is None
    assert sc._update_needed is False
    assert repr(sc) == 'Sample_Filter: no update needed'


def test_has_changed_with_none_stored_params():
    sc = StateChange(name='Sample_Filter')
    assert sc.has_changed(new_params={'param1': 'value1'}) is True
    assert sc.update_needed is True
    assert sc._stored_params == {'param1': 'value1'}
    assert repr(sc) == 'Sample_Filter: needs update'


def test_has_changed_with_same_params():
    sc = StateChange(name='Sample_Filter')
    sc.has_changed({'param1': 'value1'})
    assert sc.has_changed({'param1': 'value1'}) is False
    assert sc.update_needed is False
    assert repr(sc) == 'Sample_Filter: no update needed'


def test_has_changed_with_different_params():
    sc = StateChange(name='Sample_Filter')
    sc.has_changed({'param1': 'value1'})
    assert sc.has_changed({'param1': 'value2'}) is True
    assert sc.update_needed is True
    assert repr(sc) == 'Sample_Filter: needs update'
