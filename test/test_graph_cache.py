"""Tests for the dependency-aware cache mode (cache="graph").

Covers:
- independent branches: a parameter change only recomputes the affected branch
- linear chains: upstream changes propagate, downstream changes don't invalidate upstream
- context forward edges: a filter reading a context key is recomputed when the writer runs
- context backward edges (feedback): earlier readers are invalidated for the next run
- external context updates (GUI events / __call__(context=...)) dirty their readers
- legacy global_params filters act as conservative barriers
"""

import numpy as np

from interactive_pipe.core.context import context
from interactive_pipe.core.filter import FilterCore
from interactive_pipe.core.pipeline import PipelineCore

input_image = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def make_diamond_pipeline(counters, cache):
    """Diamond: input 0 -> branch_a (1), input 0 -> branch_b (2), merge(1, 2) -> 3."""

    def branch_a(img, gain_a=1.0):
        counters["branch_a"] += 1
        return [img * gain_a]

    def branch_b(img, gain_b=1.0):
        counters["branch_b"] += 1
        return [img * gain_b]

    def merge(img_a, img_b, blend=0.5):
        counters["merge"] += 1
        return [blend * img_a + (1 - blend) * img_b]

    filt_a = FilterCore(apply_fn=branch_a, inputs=[0], outputs=[1])
    filt_b = FilterCore(apply_fn=branch_b, inputs=[0], outputs=[2])
    filt_m = FilterCore(apply_fn=merge, inputs=[1, 2], outputs=[3])
    pip = PipelineCore(filters=[filt_a, filt_b, filt_m], inputs=[0], outputs=[3], cache=cache)
    pip.inputs = [input_image]
    return pip


def test_graph_cache_independent_branches():
    counters = {"branch_a": 0, "branch_b": 0, "merge": 0}
    pip = make_diamond_pipeline(counters, cache="graph")

    res = pip.run()
    assert counters == {"branch_a": 1, "branch_b": 1, "merge": 1}
    assert np.allclose(res[3], input_image)

    # no change -> everything served from cache
    pip.run()
    assert counters == {"branch_a": 1, "branch_b": 1, "merge": 1}

    # change branch_a parameter: branch_b must NOT be recomputed (sequential cache would recompute it)
    pip.parameters = {"branch_a": {"gain_a": 2.0}}
    res = pip.run()
    assert counters == {"branch_a": 2, "branch_b": 1, "merge": 2}
    assert np.allclose(res[3], 0.5 * 2.0 * input_image + 0.5 * input_image)

    # change merge parameter: neither branch recomputed
    pip.parameters = {"merge": {"blend": 1.0}}
    res = pip.run()
    assert counters == {"branch_a": 2, "branch_b": 1, "merge": 3}
    assert np.allclose(res[3], 2.0 * input_image)


def test_sequential_cache_recomputes_independent_branch():
    """Documents the difference: sequential cache recomputes filters after a change in list order."""
    counters = {"branch_a": 0, "branch_b": 0, "merge": 0}
    pip = make_diamond_pipeline(counters, cache=True)
    pip.run()
    pip.parameters = {"branch_a": {"gain_a": 2.0}}
    pip.run()
    # branch_b is recomputed although it does not depend on branch_a
    assert counters == {"branch_a": 2, "branch_b": 2, "merge": 2}


def test_graph_cache_linear_chain():
    counters = {"first": 0, "second": 0}

    def first(img, gain=1.0):
        counters["first"] += 1
        return [img * gain]

    def second(img, offset=0.0):
        counters["second"] += 1
        return [img + offset]

    filt1 = FilterCore(apply_fn=first, inputs=[0], outputs=[1])
    filt2 = FilterCore(apply_fn=second, inputs=[1], outputs=[2])
    pip = PipelineCore(filters=[filt1, filt2], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    pip.run()
    assert counters == {"first": 1, "second": 1}

    # downstream change leaves upstream cached
    pip.parameters = {"second": {"offset": 1.0}}
    res = pip.run()
    assert counters == {"first": 1, "second": 2}
    assert np.allclose(res[2], input_image + 1.0)

    # upstream change propagates downstream
    pip.parameters = {"first": {"gain": 3.0}}
    res = pip.run()
    assert counters == {"first": 2, "second": 3}
    assert np.allclose(res[2], 3.0 * input_image + 1.0)


def test_graph_cache_context_forward_dependency():
    """A filter reading a context key must be recomputed when the writer updates it,
    even without any variable-routing dependency between the two filters."""
    counters = {"writer": 0, "reader": 0}

    def writer(img, gain=2.0):
        counters["writer"] += 1
        context["gain"] = gain
        return [img]

    def reader(img):
        counters["reader"] += 1
        return [img * context.get("gain", 1.0)]

    filt_w = FilterCore(apply_fn=writer, inputs=[0], outputs=[1])
    filt_r = FilterCore(apply_fn=reader, inputs=[0], outputs=[2])
    pip = PipelineCore(filters=[filt_w, filt_r], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    res = pip.run()
    assert counters == {"writer": 1, "reader": 1}
    assert np.allclose(res[2], 2.0 * input_image)

    # nothing changed -> both cached (writer rewrote the same value, no spurious dirt)
    pip.run()
    assert counters == {"writer": 1, "reader": 1}

    # writer's parameter changes -> reader must see the new context value immediately
    pip.parameters = {"writer": {"gain": 5.0}}
    res = pip.run()
    assert counters == {"writer": 2, "reader": 2}
    assert np.allclose(res[2], 5.0 * input_image)


def test_graph_cache_context_backward_dependency():
    """Feedback: a reader located BEFORE the writer computes with the previous value
    (one-run delay) and is invalidated for the next run."""
    counters = {"reader": 0, "writer": 0}

    def reader(img):
        counters["reader"] += 1
        return [img * context.get("gain", 1.0)]

    def writer(img, gain=2.0):
        counters["writer"] += 1
        context["gain"] = gain
        return [img]

    filt_r = FilterCore(apply_fn=reader, inputs=[0], outputs=[1])
    filt_w = FilterCore(apply_fn=writer, inputs=[0], outputs=[2])
    pip = PipelineCore(filters=[filt_r, filt_w], inputs=[0], outputs=[1], cache="graph")
    pip.inputs = [input_image]

    # run 1: reader sees the default (gain not written yet), writer sets gain=2
    res = pip.run()
    assert counters == {"reader": 1, "writer": 1}
    assert np.allclose(res[1], input_image)

    # run 2: reader was invalidated by the feedback write, catches up with gain=2
    res = pip.run()
    assert counters == {"reader": 2, "writer": 1}
    assert np.allclose(res[1], 2.0 * input_image)

    # run 3: stable, nothing recomputes
    pip.run()
    assert counters == {"reader": 2, "writer": 1}

    # writer parameter change: writer runs, reader catches up on the following run
    pip.parameters = {"writer": {"gain": 7.0}}
    pip.run()
    assert counters == {"reader": 2, "writer": 2}
    res = pip.run()
    assert counters == {"reader": 3, "writer": 2}
    assert np.allclose(res[1], 7.0 * input_image)


def test_graph_cache_external_context_update():
    """Context updates from outside the pipeline (GUI events, __call__(context=...))
    must dirty the filters reading the updated keys."""
    counters = {"reader": 0}

    def reader(img):
        counters["reader"] += 1
        return [img * context.get("gain", 1.0)]

    filt_r = FilterCore(apply_fn=reader, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt_r], inputs=[0], outputs=[1], cache="graph")
    pip.inputs = [input_image]

    pip.run()
    pip.run()
    assert counters == {"reader": 1}

    # external write, the same way GUI backends push events: pipeline._user_context.update(...)
    pip._user_context.update({"gain": 4.0})
    res = pip.run()
    assert counters == {"reader": 2}
    assert np.allclose(res[1], 4.0 * input_image)

    # unrelated external key does not dirty the reader
    pip._user_context["unrelated"] = 123
    pip.run()
    assert counters == {"reader": 2}


def test_graph_cache_legacy_injection_tracked_precisely():
    """The injected legacy dict is wrapped in a ContextTracker: a legacy filter is
    only recomputed when a key it actually reads changes, not on any upstream change."""
    counters = {"first": 0, "legacy": 0}

    def first(img, gain=1.0):
        counters["first"] += 1
        return [img * gain]

    def legacy(img, global_params={}, offset=0.0):  # noqa: B006 - legacy API on purpose
        counters["legacy"] += 1
        return [img + global_params.get("ratio", 0.0) + offset]

    filt1 = FilterCore(apply_fn=first, inputs=[0], outputs=[1])
    filt2 = FilterCore(apply_fn=legacy, inputs=[0], outputs=[2])
    assert not filt1.uses_legacy_context
    assert filt2.uses_legacy_context

    pip = PipelineCore(filters=[filt1, filt2], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    pip.run()
    assert counters == {"first": 1, "legacy": 1}

    # 'first' does not touch the shared dict: the legacy filter stays cached
    pip.parameters = {"first": {"gain": 2.0}}
    pip.run()
    assert counters == {"first": 2, "legacy": 1}

    # no change -> everything cached
    pip.run()
    assert counters == {"first": 2, "legacy": 1}


def test_graph_cache_standalone_engine_keeps_legacy_barrier():
    """Without a PipelineCore wiring the trackers (engine used standalone),
    legacy filters keep the conservative barrier behavior."""
    from interactive_pipe.core.engine import PipelineEngine

    counters = {"first": 0, "legacy": 0}

    def first(img, gain=1.0):
        counters["first"] += 1
        return [img * gain]

    def legacy(img, global_params={}, offset=0.0):  # noqa: B006 - legacy API on purpose
        counters["legacy"] += 1
        return [img + offset]

    filt1 = FilterCore(apply_fn=first, inputs=[0], outputs=[1])
    filt2 = FilterCore(apply_fn=legacy, inputs=[0], outputs=[2])
    engine = PipelineEngine(cache="graph")

    engine.run([filt1, filt2], imglst=[input_image])
    assert counters == {"first": 1, "legacy": 1}
    filt1.values = {"gain": 2.0}
    engine.run([filt1, filt2], imglst=[input_image])
    # untracked legacy dict -> barrier: legacy filter recomputed on any upstream change
    assert counters == {"first": 2, "legacy": 2}


def test_graph_cache_class_filter_global_params_tracked():
    """Class-based filters accessing self.global_params directly (no signature hint)
    are tracked through the wrapped shared dict."""
    counters = {"GpWriter": 0, "GpReader": 0}

    class GpWriter(FilterCore):
        def apply(self, img, gain=2.0):
            counters["GpWriter"] += 1
            self.global_params["ratio"] = gain
            return [img]

    class GpReader(FilterCore):
        def apply(self, img):
            counters["GpReader"] += 1
            return [img * self.global_params.get("ratio", 1.0)]

    filt_w = GpWriter(inputs=[0], outputs=[1])
    filt_r = GpReader(inputs=[0], outputs=[2])
    assert not filt_w.uses_legacy_context  # invisible to signature inspection!
    assert not filt_r.uses_legacy_context

    pip = PipelineCore(filters=[filt_w, filt_r], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    res = pip.run()
    assert counters == {"GpWriter": 1, "GpReader": 1}
    assert np.allclose(res[2], 2.0 * input_image)

    pip.run()
    assert counters == {"GpWriter": 1, "GpReader": 1}

    # the writer's parameter changes -> the reader must see the new shared value
    pip.parameters = {"GpWriter": {"gain": 5.0}}
    res = pip.run()
    assert counters == {"GpWriter": 2, "GpReader": 2}
    assert np.allclose(res[2], 5.0 * input_image)


def test_graph_cache_global_params_replacement_resets_cache():
    """Replacing pipeline.global_params wholesale (gradio dry-run pattern) rewraps
    the tracker and invalidates every cached result."""
    counters = {"GpReader": 0}

    class GpReader(FilterCore):
        def apply(self, img):
            counters["GpReader"] += 1
            return [img * self.global_params.get("ratio", 1.0)]

    filt_r = GpReader(inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt_r], inputs=[0], outputs=[1], cache="graph")
    pip.inputs = [input_image]

    pip.run()
    pip.run()
    assert counters == {"GpReader": 1}

    pip.global_params = {"ratio": 3.0}
    res = pip.run()
    assert counters == {"GpReader": 2}
    assert np.allclose(res[1], 3.0 * input_image)
    # engine tracker follows the replacement and filters are relinked
    assert pip.engine.global_params_tracker is pip.global_params
    assert filt_r.global_params is pip.global_params


def test_graph_cache_inplace_mutation_detected():
    """In-place mutation of a stored object (append on a list obtained by read) is
    caught by fingerprinting at the filter boundary: readers recompute the same run.
    The reset-then-rebuild pattern converges (equal net content = no change)."""
    counters = {"detect": 0, "draw": 0}

    def detect(img, sigma=1.0):
        counters["detect"] += 1
        context["boxes"] = []
        context["boxes"].append(sigma)  # in-place mutation after the reset write
        return [img]

    def draw(img):
        counters["draw"] += 1
        return [img + sum(context["boxes"])]

    filt_d = FilterCore(apply_fn=detect, inputs=[0], outputs=[1])
    filt_v = FilterCore(apply_fn=draw, inputs=[0], outputs=[2])
    pip = PipelineCore(filters=[filt_d, filt_v], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    res = pip.run()
    assert counters == {"detect": 1, "draw": 1}
    assert np.allclose(res[2], input_image + 1.0)

    # detect reads AND writes "boxes" (self feedback edge): one settle run replays it,
    # but the net content is identical so draw stays cached
    pip.run()
    assert counters == {"detect": 2, "draw": 1}
    pip.run()
    assert counters == {"detect": 2, "draw": 1}

    # detect recomputes with a new sigma: draw must see the new boxes the same run
    pip.parameters = {"detect": {"sigma": 2.0}}
    res = pip.run()
    assert counters == {"detect": 3, "draw": 2}
    assert np.allclose(res[2], input_image + 2.0)

    # one settle run for the self edge, then stable again
    pip.run()
    assert counters == {"detect": 4, "draw": 2}
    pip.run()
    assert counters == {"detect": 4, "draw": 2}


def test_graph_cache_accumulator_always_recomputes():
    """A filter accumulating state in the context (reads and grows the same key) is a
    genuinely stateful filter: it recomputes every run, and its readers follow."""
    counters = {"accumulate": 0, "display": 0}

    def accumulate(img, step=1.0):
        counters["accumulate"] += 1
        context["history"].append(step)  # grows forever: never the same net content
        return [img]

    def display(img):
        counters["display"] += 1
        return [img + len(context["history"])]

    filt_a = FilterCore(apply_fn=accumulate, inputs=[0], outputs=[1])
    filt_s = FilterCore(apply_fn=display, inputs=[0], outputs=[2])
    pip = PipelineCore(filters=[filt_a, filt_s], inputs=[0], outputs=[2], context={"history": []}, cache="graph")
    pip.inputs = [input_image]

    res = pip.run()
    assert counters == {"accumulate": 1, "display": 1}
    assert np.allclose(res[2], input_image + 1)

    res = pip.run()
    assert counters == {"accumulate": 2, "display": 2}
    assert np.allclose(res[2], input_image + 2)


def test_graph_cache_equal_value_rewrite_no_spurious_recompute():
    """Rewriting an equal value (fresh object, same content) must not invalidate readers."""
    counters = {"writer": 0, "reader": 0}

    def writer(img, gain=2.0, brightness=1.0):
        counters["writer"] += 1
        context["meta"] = {"labels": ["a", "b"], "gain": gain}  # fresh dict every run
        return [img * brightness]

    def reader(img):
        counters["reader"] += 1
        return [img + context["meta"]["gain"]]

    filt_w = FilterCore(apply_fn=writer, inputs=[0], outputs=[1])
    filt_r = FilterCore(apply_fn=reader, inputs=[0], outputs=[2])
    pip = PipelineCore(filters=[filt_w, filt_r], inputs=[0], outputs=[2], cache="graph")
    pip.inputs = [input_image]

    pip.run()
    assert counters == {"writer": 1, "reader": 1}

    # brightness changes -> writer recomputes but rewrites identical meta content:
    # reader stays cached
    pip.parameters = {"writer": {"brightness": 3.0}}
    pip.run()
    assert counters == {"writer": 2, "reader": 1}

    # gain changes -> meta content differs -> reader recomputes
    pip.parameters = {"writer": {"gain": 9.0}}
    res = pip.run()
    assert counters == {"writer": 3, "reader": 2}
    assert np.allclose(res[2], input_image + 9.0)


def test_graph_cache_external_inplace_mutation_detected():
    """Mutating a stored numpy array in place from outside the pipeline (GUI callback,
    stashed reference) is caught by the run-start fingerprint sweep."""
    counters = {"reader": 0}
    lut = np.array([2.0, 3.0])

    def reader(img):
        counters["reader"] += 1
        return [img * context["lut"][0]]

    filt_r = FilterCore(apply_fn=reader, inputs=[0], outputs=[1])
    pip = PipelineCore(filters=[filt_r], inputs=[0], outputs=[1], context={"lut": lut}, cache="graph")
    pip.inputs = [input_image]

    res = pip.run()
    pip.run()
    assert counters == {"reader": 1}
    assert np.allclose(res[1], 2.0 * input_image)

    # in-place mutation through the original reference, no dict operation at all
    lut[0] = 7.0
    res = pip.run()
    assert counters == {"reader": 2}
    assert np.allclose(res[1], 7.0 * input_image)


def test_graph_cache_results_match_no_cache():
    """Graph cache must produce the same results as running without cache."""
    for cache in [False, "graph"]:
        counters = {"branch_a": 0, "branch_b": 0, "merge": 0}
        pip = make_diamond_pipeline(counters, cache=cache)
        pip.run()
        pip.parameters = {"branch_b": {"gain_b": 3.0}, "merge": {"blend": 0.25}}
        res = pip.run()
        assert np.allclose(res[3], 0.25 * input_image + 0.75 * 3.0 * input_image)
