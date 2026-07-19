"""Runtime tracking of user-context reads and writes, powering the dependency-aware cache.

When a pipeline runs with ``cache="graph"``, the user context (accessed by filters through
the ``context`` proxy or ``get_context()``) is wrapped in a :class:`ContextTracker`.
The tracker records which filter reads and which filter writes each context key, so the
engine can invalidate the cached result of a filter whenever a context key it relies on
has been updated - even though this data dependency is invisible to the AST call graph.

Change detection combines two mechanisms:

- dict instrumentation attributes reads and writes to the running filter;
- content fingerprints (:func:`_fingerprint`) catch what instrumentation cannot see:
  in-place mutation of stored objects (``context["boxes"].append(...)``) is detected by
  re-fingerprinting every key a filter accessed when it finishes, and mutations happening
  outside any filter (GUI callbacks, stashed references) are detected at the start of the
  next run (:meth:`ContextTracker.detect_silent_changes`).

Known limitations (conservative by design, documented for users of ``cache="graph"``):

- A value mutated through a reference stashed in a previous run is only detected at the
  next run start: the runs in between may serve one stale frame for its readers.
- ``dict(context)`` style copies bypass instrumentation; prefer explicit key access or
  ``context.items()`` which registers the filter as a reader of every key.
- Unpicklable values cannot be fingerprinted: their key counts as changed on every check,
  so their readers are recomputed on every run (never stale, but never cached either).
"""

import hashlib
import pickle
from typing import Any, Dict, Optional, Set

# cache modes enabling dependency-aware caching; "graph-strict" additionally returns
# numpy arrays as read-only views so in-place mutation raises at the offending line
GRAPH_CACHE_MODES = ("graph", "graph-strict")

_UNSET = object()


def _fingerprint(value: Any) -> Any:
    """Content digest used to decide whether a context value actually changed.

    Detects in-place mutation that dict instrumentation alone cannot see, and
    avoids spurious invalidation when a filter rewrites an equal value.

    - primitives: the value itself (with its type, so True != 1)
    - numpy arrays: shape + dtype + hash of the raw buffer (one fast memory pass)
    - anything else: hash of its pickle serialization
    - unpicklable values: a unique marker that never compares equal, so the key is
      conservatively considered changed on every check (extra recompute, never stale)
    """
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return ("primitive", type(value).__name__, value)
    value_type = type(value)
    if value_type.__module__ == "numpy" and value_type.__name__ == "ndarray":
        return ("ndarray", value.shape, str(value.dtype), hashlib.sha1(value.tobytes()).digest())
    try:
        payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        return object()
    return ("pickle", hashlib.sha1(payload).digest())


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
    - A key only counts as changed when its content fingerprint differs from the
      baseline (the net effect of the filter, judged at the filter boundary), so
      rewriting an equal value never invalidates readers, while in-place mutations
      are reliably detected.
    """

    def __init__(
        self,
        initial: Optional[Dict[str, Any]] = None,
        ignore_prefix: Optional[str] = None,
        strict: bool = False,
    ):
        super().__init__(initial or {})
        # strict mode: reads return numpy arrays as read-only views, so in-place
        # mutation raises a ValueError at the offending user line instead of being
        # silently absorbed by fingerprint detection
        self._strict = strict
        self._reads: Dict[str, Set[Any]] = {}  # filter name -> keys it reads
        self._reads_all: Set[str] = set()  # filters enumerating the whole context
        self._current: Optional[str] = None  # name of the filter currently running
        self._external_changes: Set[Any] = set()  # keys changed outside any filter
        self._current_touched: Set[Any] = set()  # keys accessed by the current filter
        self._current_read_all = False  # current filter enumerated the whole context
        # keys starting with this prefix are not tracked at all
        # (defensive exclusion of framework-internal keys when wrapping shared dicts)
        self._ignore_prefix = ignore_prefix
        # content fingerprints: baseline for change detection, including in-place mutation
        self._digests: Dict[Any, Any] = {}
        for key in dict.keys(self):
            if not self._ignored(key):
                self._digests[key] = _fingerprint(dict.__getitem__(self, key))

    def _ignored(self, key: Any) -> bool:
        return self._ignore_prefix is not None and isinstance(key, str) and key.startswith(self._ignore_prefix)

    def _wrap_readonly(self, value: Any) -> Any:
        if not self._strict:
            return value
        value_type = type(value)
        if value_type.__module__ == "numpy" and value_type.__name__ == "ndarray":
            view = value.view()
            view.flags.writeable = False
            return view
        return value

    # ------------------------------------------------------------------
    # Engine hooks
    # ------------------------------------------------------------------
    def begin_filter(self, name: str) -> None:
        """Attribute subsequent context accesses to the given filter."""
        self._current = name
        self._current_touched = set()
        self._current_read_all = False

    def finish_filter(self) -> Set[Any]:
        """Stop attributing accesses and return the keys the filter NET-changed.

        Every key the filter accessed is re-fingerprinted and compared against the
        stored baseline, so that:
        - in-place mutation of a stored object (context["boxes"].append(...)) counts
          as a change even though no dict write ever happened;
        - only the net effect matters: a filter resetting then rebuilding an equal
          value (context["boxes"] = []; ...append(...)) leaves the key unchanged,
          which lets feedback/self loops converge instead of recomputing forever.
        """
        touched = self._current_touched
        if self._current_read_all:
            touched = touched | {key for key in dict.keys(self) if not self._ignored(key)}
        changes: Set[Any] = set()
        for key in touched:
            if dict.__contains__(self, key):
                new_digest = _fingerprint(dict.__getitem__(self, key))
                old_digest = self._digests.get(key, _UNSET)
                self._digests[key] = new_digest
                if old_digest is _UNSET or old_digest != new_digest:
                    changes.add(key)
            elif self._digests.pop(key, _UNSET) is not _UNSET:
                # key deleted by this filter
                changes.add(key)
        self._current = None
        self._current_touched = set()
        self._current_read_all = False
        return changes

    def detect_silent_changes(self) -> Set[Any]:
        """Re-fingerprint every key having a registered reader and return those whose
        content changed through untracked paths since the last check (in-place mutation
        of a stored object between runs: GUI callbacks, stashed references...).

        Called by the engine at the start of each run.
        """
        monitored: Set[Any] = set()
        for keys in self._reads.values():
            monitored |= keys
        if self._reads_all:
            monitored |= {key for key in dict.keys(self) if not self._ignored(key)}
        changed = set()
        for key in monitored:
            if not dict.__contains__(self, key):
                continue
            new_digest = _fingerprint(dict.__getitem__(self, key))
            old_digest = self._digests.get(key, _UNSET)
            self._digests[key] = new_digest
            if old_digest is not _UNSET and old_digest != new_digest:
                changed.add(key)
        return changed

    def report_aborted_run(self, changed_keys: Set[Any]) -> None:
        """Persist an aborted run's context changes as external changes.

        When a filter raises, the run dies before downstream readers consume the keys
        already changed this run (and before feedback edges are processed) - but the
        fingerprint baselines were already advanced. Re-injecting the changes as
        external ones makes the next run invalidate every reader of those keys.
        """
        self._external_changes |= changed_keys | self.finish_filter()

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
        if self._current is not None and not self._ignored(key):
            self._reads.setdefault(self._current, set()).add(key)
            self._current_touched.add(key)

    def _record_read_all(self) -> None:
        if self._current is not None:
            self._reads_all.add(self._current)
            self._current_read_all = True

    def _record_write(self, key: Any, new_value: Any = _UNSET) -> None:
        if self._ignored(key):
            return
        if self._current is not None:
            # net change decided at finish_filter by fingerprint comparison
            self._current_touched.add(key)
            return
        # write outside any filter (GUI events, user code between runs)
        if new_value is _UNSET:
            # deletion: a change when the key was known
            if self._digests.pop(key, _UNSET) is not _UNSET:
                self._external_changes.add(key)
        else:
            new_digest = _fingerprint(new_value)
            old_digest = self._digests.get(key, _UNSET)
            self._digests[key] = new_digest
            if old_digest is _UNSET or old_digest != new_digest:
                self._external_changes.add(key)

    # ------------------------------------------------------------------
    # Instrumented dict interface
    # ------------------------------------------------------------------
    def __getitem__(self, key):
        self._record_read(key)
        return self._wrap_readonly(dict.__getitem__(self, key))

    def get(self, key, default=None):
        self._record_read(key)
        if dict.__contains__(self, key):
            return self._wrap_readonly(dict.__getitem__(self, key))
        return default

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
        return self._wrap_readonly(dict.setdefault(self, key, default))

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
