"""Runtime tracking of user-context reads and writes, powering the dependency-aware cache.

When a pipeline runs with ``cache="graph"``, the user context (accessed by filters through
the ``context`` proxy or ``get_context()``) is wrapped in a :class:`ContextTracker`.
The tracker records which filter reads and which filter writes each context key, so the
engine can invalidate the cached result of a filter whenever a context key it relies on
has been updated - even though this data dependency is invisible to the AST call graph.

Known limitations (conservative by design, documented for users of ``cache="graph"``):

- In-place mutation of a stored value (``context["arr"][0] = 5``) is only seen as a read.
  Assign a new value (``context["arr"] = new_arr``) so the change is detected.
- Re-assigning the exact same object is treated as a change (it may have been mutated
  in place), which can cause extra recomputations but never stale results.
- ``dict(context)`` style copies bypass instrumentation; prefer explicit key access or
  ``context.items()`` which registers the filter as a reader of every key.
- Class-based filters touching ``self.global_params`` directly inside ``apply`` are not
  tracked; prefer the ``context`` proxy API.
"""

from typing import Any, Dict, Optional, Set

_UNSET = object()


class ContextTracker(dict):
    """Dict recording per-filter reads and writes of the user context.

    - Accesses performed while a filter runs (between :meth:`begin_filter` and
      :meth:`finish_filter`) are attributed to that filter; accesses outside any filter
      (GUI event handlers, ``pipeline(..., context={...})`` updates) are recorded as
      *external changes* consumed by the engine at the start of the next run.
    - Read tracking is cumulative across runs: once a filter is known to read a key,
      it stays registered as a reader of that key.
    - Whole-dict enumeration (``keys``/``values``/``items``/iteration/``len``) registers
      the current filter as a reader of every key (conservative).
    - A write only counts as a change when the new value compares different from the
      stored one; when the comparison is ambiguous (e.g. numpy arrays) the write is
      conservatively considered a change.
    """

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        super().__init__(initial or {})
        self._reads: Dict[str, Set[Any]] = {}  # filter name -> keys it reads
        self._reads_all: Set[str] = set()  # filters enumerating the whole context
        self._current: Optional[str] = None  # name of the filter currently running
        self._current_changes: Set[Any] = set()  # keys changed by the current filter
        self._external_changes: Set[Any] = set()  # keys changed outside any filter

    # ------------------------------------------------------------------
    # Engine hooks
    # ------------------------------------------------------------------
    def begin_filter(self, name: str) -> None:
        """Attribute subsequent context accesses to the given filter."""
        self._current = name
        self._current_changes = set()

    def finish_filter(self) -> Set[Any]:
        """Stop attributing accesses and return the keys changed by the filter."""
        changes = self._current_changes
        self._current = None
        self._current_changes = set()
        return changes

    def consume_external_changes(self) -> Set[Any]:
        """Return keys changed outside of any filter since the last run, and reset."""
        changes = self._external_changes
        self._external_changes = set()
        return changes

    def reads_changed_keys(self, filter_name: str, changed_keys: Set[Any]) -> bool:
        """Check whether a filter is a known reader of any of the changed keys."""
        if not changed_keys:
            return False
        if filter_name in self._reads_all:
            return True
        return bool(self._reads.get(filter_name, set()) & changed_keys)

    def readers_of(self, key: Any) -> Set[str]:
        """Names of all filters known to read the given key."""
        readers = set(self._reads_all)
        for name, keys in self._reads.items():
            if key in keys:
                readers.add(name)
        return readers

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------
    def _record_read(self, key: Any) -> None:
        if self._current is not None:
            self._reads.setdefault(self._current, set()).add(key)

    def _record_read_all(self) -> None:
        if self._current is not None:
            self._reads_all.add(self._current)

    def _record_write(self, key: Any, new_value: Any = _UNSET) -> None:
        changed = True
        if new_value is not _UNSET and dict.__contains__(self, key):
            old_value = dict.__getitem__(self, key)
            if old_value is not new_value:
                try:
                    changed = bool(old_value != new_value)
                except Exception:
                    # ambiguous comparison (e.g. numpy arrays): assume changed
                    changed = True
            # identical object: keep changed=True, it may have been mutated in place
        if changed:
            if self._current is not None:
                self._current_changes.add(key)
            else:
                self._external_changes.add(key)

    # ------------------------------------------------------------------
    # Instrumented dict interface
    # ------------------------------------------------------------------
    def __getitem__(self, key):
        self._record_read(key)
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        self._record_read(key)
        return dict.get(self, key, default)

    def __contains__(self, key):
        self._record_read(key)
        return dict.__contains__(self, key)

    def __setitem__(self, key, value):
        self._record_write(key, value)
        dict.__setitem__(self, key, value)

    def setdefault(self, key, default=None):
        self._record_read(key)
        if not dict.__contains__(self, key):
            self._record_write(key, default)
        return dict.setdefault(self, key, default)

    def __delitem__(self, key):
        if dict.__contains__(self, key):
            self._record_write(key)
        dict.__delitem__(self, key)

    def pop(self, key, *args):
        self._record_read(key)
        if dict.__contains__(self, key):
            self._record_write(key)
        return dict.pop(self, key, *args)

    def popitem(self):
        self._record_read_all()
        key, value = dict.popitem(self)
        self._record_write(key)
        return key, value

    def update(self, *args, **kwargs):
        incoming = dict(*args, **kwargs)
        for key, value in incoming.items():
            self._record_write(key, value)
        dict.update(self, incoming)

    def clear(self):
        for key in list(dict.keys(self)):
            self._record_write(key)
        dict.clear(self)

    def keys(self):
        self._record_read_all()
        return dict.keys(self)

    def values(self):
        self._record_read_all()
        return dict.values(self)

    def items(self):
        self._record_read_all()
        return dict.items(self)

    def __iter__(self):
        self._record_read_all()
        return dict.__iter__(self)

    def __len__(self):
        self._record_read_all()
        return dict.__len__(self)
