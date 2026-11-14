"""The sweep caption omits only the swept parameter, not every parameter sharing its name."""

import numpy as np

from interactive_pipe import interactive
from interactive_pipe.headless import explore
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(gain=(1.0, [0.0, 3.0]))
def cap_amplify(img, gain=1.0):
    return img * gain


@interactive(gain=(0.5, [0.0, 1.0]), flip=True)
def cap_blend(img, gain=0.5, flip=True):
    return img * gain


def caption_pipeline(img):
    a = cap_amplify(img)
    b = cap_blend(a)
    return b


def _sweep_caption(monkeypatch, tmp_path, **kwargs):
    captured = {}
    original = explore.render_sweep

    def spy(*args, **render_kwargs):
        captured["caption"] = render_kwargs.get("caption")
        return original(*args, **render_kwargs)

    monkeypatch.setattr(explore, "render_sweep", spy)
    pipe = HeadlessPipeline.from_function(caption_pipeline)
    pipe.sweep(tmp_path / "sweep.png", np.ones((4, 4)) * 0.5, **kwargs)
    return captured["caption"]


def test_sweeping_one_filter_keeps_the_other_filters_parameter(monkeypatch, tmp_path):
    caption = _sweep_caption(monkeypatch, tmp_path, **{"cap_amplify.gain": [0.5, 1.0, 2.0]})
    assert caption == "cap_blend: gain=0.5, flip=True"


def test_sweeping_a_control_name_keeps_the_other_filter(monkeypatch, tmp_path):
    # both filters have `gain`: the controls are named cap_amplify.gain / cap_blend.gain
    caption = _sweep_caption(monkeypatch, tmp_path, **{"cap_blend.gain": [0.2, 0.8]})
    assert caption == "cap_amplify: gain=1\ncap_blend: flip=True"


def test_sweeping_a_bare_name_omits_it_everywhere(monkeypatch, tmp_path):
    caption = _sweep_caption(monkeypatch, tmp_path, gain=[0.5, 1.0])
    assert caption == "cap_blend: flip=True"
