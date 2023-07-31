import logging
from copy import deepcopy
from typing import Any


class CachedResults:
    """
    Helper class to store the results of a Filter.

    The overall purpose of these classes is to prevent unnecessary computations by reusing the
    results of previous filter operations when the input parameters have not changed. 
    This is accomplished by storing the results of the filter operations and the parameters
    used in those operations, and checking for changes in the parameters
    before re-computing the results.

    Each Filter has its own CachedResults class
    - uses a StateChange to detect if parameters/sliders values have been modified
    - update results only when the state of the sliders has been changed
    - keep cached Filters results in memory

    Please note that only pointers are copied when updating the cache, no deepcopy is performed here

    Underlying class used in the interactive pipe cache mechanism.
    """

    def __init__(self, name: str = None):
        self.name = name
        self.result = None
        self.state_change = StateChange(name=name)
        self._force_change = False

    @property
    def force_change(self) -> bool:
        return self._force_change

    @force_change.setter
    def force_change(self, value: bool) -> None:
        self._force_change = value

    @property
    def has_changed(self, new_params: Any) -> bool:
        """
        Check if the parameters have changed and mark an update as needed if they have.

        :param new_params: The new parameters to check.
        :return: True if an update is needed or False otherwise.
        """
        if self.result is None:  # if no result force initialization
            self.force_change = True
        change_state_from_params_check = self.state_change.has_changed(
            new_params)
        if self.force_change:
            self.state_change.update_needed = True
            self.force_change = False
            change_state_from_params_check = True
        return change_state_from_params_check

    def update(self, new_result: Any) -> None:
        """
        Update the result.

        :param new_result: The new result to store.
        """
        if self.name is not None:
            logging.debug(f"OVERRIDE CACHE RESULTS - {self.name}")
        self.result = new_result

    def __repr__(self) -> str:
        return self.name


class StateChange():
    """
    Helper class to check if parameters whether or not input parameters have been updated.
    Underlying class used in the interactive pipe cache mechanism
    """

    def __init__(self, name=None):
        self.name = name
        self.stored_params = None
        self.update_needed = False

    def has_changed(self, new_params) -> bool:
        if self.stored_params is None or new_params != self.stored_params:
            self.stored_params = deepcopy(new_params)
            self.update_needed = True
        else:
            self.update_needed = False
        return self.update_needed
