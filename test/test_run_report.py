"""Per-filter timings of the last run (RunReport) and the profiling action."""

import numpy as np
import pytest

from interactive_pipe import interactive
from interactive_pipe.core.engine import FilterError, RunReport
from interactive_pipe.graphical.gui import InteractivePipeGUI
from interactive_pipe.graphical.window import format_run_status, format_timings_table
from interactive_pipe.headless.pipeline import HeadlessPipeline


@interactive(gain=(0.5, [0.0, 1.0]))
def report_gain(img, gain=0.5):
    return img * gain


@interactive(offset=(0.0, [-1.0, 1.0]))
def report_offset(img, offset=0.0):
    return img + offset


@interactive(fail=(False,))
def report_maybe_fail(img, fail=False):
    if fail:
        raise ValueError("boom")
    return img


def report_pipeline(img):
    gained = report_gain(img)
    out = report_offset(gained)
    return out


def failing_pipeline(img):
    gained = report_gain(img)
    out = report_maybe_fail(gained)
    return out


def test_report_is_none_before_first_run():
    pipeline = HeadlessPipeline.from_function(report_pipeline, inputs=["img"])
    assert pipeline.last_run_report is None


def test_report_lists_every_filter_and_cached_ones():
    pipeline = HeadlessPipeline.from_function(report_pipeline, inputs=["img"], cache=True)
    pipeline.inputs = [np.ones((4, 4))]
    pipeline.run()
    report = pipeline.last_run_report
    assert isinstance(report, RunReport)
    assert list(report.timings) == ["report_gain", "report_offset"]
    assert report.cached == set()
    assert report.total >= sum(report.timings.values()) - 1e-6
    assert report.failed is None

    pipeline.parameters = {"report_offset": {"offset": 0.1}}
    pipeline.run()
    report = pipeline.last_run_report
    assert report.cached == {"report_gain"}
    assert report.timings["report_gain"] == 0.0
    assert report.num_filters == 2


def test_report_flags_the_failing_filter():
    pipeline = HeadlessPipeline.from_function(failing_pipeline, inputs=["img"])
    pipeline.inputs = [np.ones((4, 4))]
    pipeline.parameters = {"report_maybe_fail": {"fail": True}}
    with pytest.raises(FilterError):
        pipeline.run()
    assert pipeline.last_run_report.failed == "report_maybe_fail"
    assert format_run_status(pipeline.last_run_report) == "error in report_maybe_fail"
    lines = format_timings_table(pipeline.last_run_report)
    assert any(line.startswith("report_maybe_fail") and line.rstrip().endswith("FAILED") for line in lines)
    assert any(line.startswith("total") and "until the error" in line for line in lines)
    assert lines[-1] == "Run failed at report_maybe_fail: later filters did not run."


def test_status_and_table_formatting():
    report = RunReport(timings={"a": 0.010, "bb": 0.0}, cached={"bb"}, total=0.0123)
    assert format_run_status(report) == "run 12.3 ms · 2 filters · 1 cached"
    assert format_run_status(None) == ""
    lines = format_timings_table(report)
    assert lines[0].split() == ["filter", "ms", "cached"]
    assert any(line.startswith("bb") and line.rstrip().endswith("yes") for line in lines)
    assert lines[-1].startswith("total") and "12.30" in lines[-1]
    assert format_timings_table(None) == ["No pipeline run yet."]


class _MessageGUI(InteractivePipeGUI):
    def init_app(self, **kwargs):
        self.messages = []
        self.set_default_key_bindings()

    def print_message(self, message_list):
        self.messages.append(message_list)


def test_t_key_prints_the_timings_table():
    pipeline = HeadlessPipeline.from_function(report_pipeline, inputs=["img"])
    gui = _MessageGUI(pipeline=pipeline)
    gui.pipeline.inputs = [np.ones((2, 2))]
    gui.pipeline.run()
    gui.on_press("t")
    assert gui.messages and "report_offset" in "\n".join(gui.messages[-1])
