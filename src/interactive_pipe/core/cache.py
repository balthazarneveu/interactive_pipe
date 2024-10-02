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

    Please note that if you use safe_buffer_deepcopy=False,
    only pointers are copied when updating the cache, no deepcopy is performed here.
    You should only use safe_buffer_deepcopy=False
    if you're 100% sure you don't do inplace modifications.

    Underlying class used in the interactive pipe cache mechanism.
    """

    def __init__(self, name: str = None, safe_buffer_deepcopy: bool = True):
        self.name = name
        self.result = None
        self.state_change = StateChange(name=name)
        self._force_change = False
        self.safe_buffer_deepcopy = safe_buffer_deepcopy

    @property
    def force_change(self) -> bool:
        return self._force_change

    @force_change.setter
    def force_change(self, value: bool) -> None:
        self._force_change = value

    def has_changed(self, new_params: Any) -> bool:
        """
        Check if the parameters have changed and mark an update as needed if they have.

        :param new_params: The new parameters to check.
        :return: True if an update is needed or False otherwise.
        """
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
        self.result = new_result if not self.safe_buffer_deepcopy else deepcopy(
            new_result)

    def __repr__(self) -> str:
        return self.name


class StateChange:
    """
    Helper class to check whether or not input parameters have been updated.

    Underlying class used in the interactive pipe cache mechanism.
    """

    def __init__(self, name: str = None):
        self.name = name
        self._stored_params = None
        self._update_needed = False

    def has_changed(self, new_params: Any) -> bool:
        """
        Check if the new parameters are different from the stored parameters.

        :param new_params: The new parameters to check.
        :return: True if the parameters have changed or False otherwise.
        """
        if self._stored_params is None or new_params != self._stored_params:
            self._stored_params = deepcopy(new_params)
            self._update_needed = True
        else:
            self._update_needed = False
        return self._update_needed

    @property
    def update_needed(self) -> bool:
        return self._update_needed

    @update_needed.setter
    def update_needed(self, value: bool) -> None:
        self._update_needed = value

    def __repr__(self) -> str:
        return f"{self.name}: " + ("needs update" if self.update_needed else "no update needed")
