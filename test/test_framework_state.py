"""Unit tests for core/framework_state.py (tech-debt item 2)."""

import gc
import weakref

import numpy as np

from interactive_pipe import interactive, layout
from interactive_pipe.core.filter import FilterCore, PureFilter
from interactive_pipe.core.framework_state import AudioBindings, FrameworkState
from interactive_pipe.core.pipeline import PipelineCore


def test_audio_defaults_are_noops():
    state = FrameworkState()
    # Must not raise outside a GUI (same silent-skip as the legacy None checks)
    state.audio.set_audio("anything.mp3")
    state.audio.play()
    state.audio.pause()
    state.audio.stop()


def test_snapshot_restore_round_trip():
    state = FrameworkState()
    state.output_styles["out"] = {"title": "before"}
    state.events["evt"] = True
    sentinel_calls = []
    state.audio.play = lambda: sentinel_calls.append("play")

    snap = state.snapshot()
    # Snapshot dicts are independent copies...
    state.output_styles["out"]["title"] = "after"
    state.events["evt"] = False
    assert snap.output_styles["out"]["title"] == "before"
    assert snap.events["evt"] is True
    # ...but audio callables are kept by reference (no deepcopy of callbacks)
    assert snap.audio.play is state.audio.play

    state.restore(snap)
    assert state.output_styles["out"]["title"] == "before"
    assert state.events["evt"] is True
    state.audio.play()
    assert sentinel_calls == ["play"]


def test_pipeline_backref_is_weak():
    def passthrough(img):
        return img

    filt = FilterCore(apply_fn=passthrough, inputs=[0], outputs=[[0]])
    pipeline = PipelineCore(filters=[filt], inputs=[0], outputs=[[0]], cache=False)
    state = pipeline.framework_state
    assert state.pipeline is pipeline

    pipeline_ref = weakref.ref(pipeline)
    # Drop the strong references the test holds; the state must not keep the
    # pipeline alive (this was the legacy __app/__pipeline reference cycle)
    filt.framework_state = FrameworkState()  # detach the filter's share
    del pipeline, filt
    gc.collect()
    assert pipeline_ref() is None
    assert state.pipeline is None


def test_pipeline_shares_state_with_filters():
    @interactive()
    def styled(img):
        layout.style("styled_out", title="shared state works")
        return img

    filt = FilterCore(apply_fn=styled, inputs=[0], outputs=["styled_out"])
    pipeline = PipelineCore(filters=[filt], inputs=[0], outputs=[["styled_out"]], cache=False)
    assert filt.framework_state is pipeline.framework_state
    pipeline.inputs = [np.ones((4, 4))]
    pipeline.run()
    assert pipeline.framework_state.output_styles["styled_out"]["title"] == "shared state works"


def test_standalone_filter_owns_default_state():
    def styled(img):
        layout.style("solo", title="standalone")
        return [img]

    filt = PureFilter(apply_fn=styled)
    filt.run(np.ones((4, 4)))
    assert filt.framework_state.output_styles["solo"]["title"] == "standalone"


def test_bindings_dataclass_shape():
    bindings = AudioBindings()
    assert callable(bindings.set_audio)
    assert callable(bindings.play)
    assert callable(bindings.pause)
    assert callable(bindings.stop)
