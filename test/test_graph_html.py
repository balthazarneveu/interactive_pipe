"""graph_representation: dependency-free HTML diagram of the pipeline (graph_html.py)."""

import re
import sys
from html.parser import HTMLParser

import pytest

from interactive_pipe import Control, interactive, interactive_pipeline
from interactive_pipe.headless.graph_html import graph_html, layout_graph, pipeline_graph


@interactive(gain=Control(1.0, [0.0, 2.0], name="exposure"))
def gh_expose(img, gain=1.0):
    """Multiply the image."""
    return img * gain


@interactive(mode=Control("gray", ["gray", "sepia"]))
def gh_tone(img, mode="gray", fixed=3):
    return img, img


def gh_blend(a, b):
    return (a + b) / 2


def gh_generate():
    return 1.0


def gh_pipeline(img, other):
    exposed = gh_expose(img)
    toned, mask = gh_tone(exposed)
    blended = gh_blend(toned, other)
    noise = gh_generate()
    return [[exposed, blended], [mask, img, noise]]


@pytest.fixture
def pipe():
    return interactive_pipeline(gui=None)(gh_pipeline)


EXPECTED_EDGES = {
    ("in:img", "filter:0", "img"),
    ("filter:0", "filter:1", "exposed"),
    ("filter:1", "filter:2", "toned"),
    ("in:other", "filter:2", "other"),
    ("filter:0", "out:0", "exposed"),
    ("filter:2", "out:1", "blended"),
    ("filter:1", "out:2", "mask"),
    ("in:img", "out:3", "img"),
    ("filter:3", "out:4", "noise"),
}


class _Checker(HTMLParser):
    """Collects tags and checks that every non-void element is closed in order."""

    VOID = {"meta", "br", "img", "input", "link", "hr"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.tags = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}>, open: {self.stack[-3:]}")
        else:
            self.stack.pop()


def test_pipeline_graph_nodes_and_edges(pipe):
    graph = pipeline_graph(pipe)
    kinds = [(node.kind, node.name) for node in graph.nodes]
    assert kinds == [
        ("input", "img"),
        ("input", "other"),
        ("filter", "gh_expose"),
        ("filter", "gh_tone"),
        ("filter", "gh_blend"),
        ("filter", "gh_generate"),
        ("output", "exposed"),
        ("output", "blended"),
        ("output", "mask"),
        ("output", "img"),
        ("output", "noise"),
    ]
    assert {(edge.source, edge.target, edge.label) for edge in graph.edges} == EXPECTED_EDGES
    expose = graph.nodes[2]
    assert expose.doc == "Multiply the image."
    assert expose.lines == [("gain = 1", "exposure [0, 2]")]
    tone = graph.nodes[3]
    assert tone.lines == [("mode = gray", "{gray, sepia}"), ("fixed = 3", "fixed")]


def test_layout_has_no_overlap_and_flows_downward(pipe):
    graph = pipeline_graph(pipe)
    layout = layout_graph(graph)
    boxes = list(layout.boxes.values())
    for idx, first in enumerate(boxes):
        assert first.x - first.width / 2 >= 0 and first.x + first.width / 2 <= layout.width
        assert first.y >= 0 and first.y + first.height <= layout.height
        for second in boxes[idx + 1 :]:
            separate_x = abs(first.x - second.x) >= (first.width + second.width) / 2
            separate_y = first.y + first.height <= second.y or second.y + second.height <= first.y
            assert separate_x or separate_y, (first.id, second.id)
    for edge in graph.edges:
        assert layout.boxes[edge.source].layer < layout.boxes[edge.target].layer


def test_graph_representation_writes_standalone_html(pipe, tmp_path):
    path = pipe.graph_representation(tmp_path / "graph")
    assert path == tmp_path / "graph.html"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>")
    checker = _Checker()
    checker.feed(text)
    checker.close()
    assert checker.errors == [] and checker.stack == []
    tags = [tag for tag, _attrs in checker.tags]
    assert tags.count("svg") == 1 and "style" in tags and "script" in tags
    # self-contained: no external resource, no URL at all
    assert not re.search(r"https?://|//cdn|<link|\ssrc=|@import", text)
    nodes = {attrs["data-name"] for tag, attrs in checker.tags if "data-name" in attrs}
    assert {"gh_expose", "gh_tone", "gh_blend", "gh_generate", "img", "other", "mask", "noise"} <= nodes
    names = {attrs["data-id"]: attrs["data-name"] for tag, attrs in checker.tags if "data-id" in attrs}
    edges = {
        (attrs["data-src"], attrs["data-dst"], attrs["data-label"])
        for tag, attrs in checker.tags
        if attrs.get("class") == "edge"
    }
    assert edges == EXPECTED_EDGES
    assert set(names) >= {node for edge in edges for node in edge[:2]}
    assert "prefers-color-scheme: dark" in text


def test_graph_representation_default_path_and_escaping(tmp_path, monkeypatch):
    @interactive()
    def gh_angle(img, label="<b>&"):
        return img

    def gh_weird(img):
        out = gh_angle(img)
        return out

    pipe = interactive_pipeline(gui=None)(gh_weird)
    pipe.name = "my pipe<1>"
    monkeypatch.chdir(tmp_path)
    path = pipe.graph_representation()
    assert path.name == "my_pipe_1_.html" and path.exists()
    text = path.read_text(encoding="utf-8")
    assert "<b>&" not in text and "&lt;b&gt;&amp;" in text
    assert "my pipe&lt;1&gt;" in text


def test_view_opens_the_browser_unless_snapshot(pipe, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)
    path = pipe.graph_representation(tmp_path / "g.html", view=True)
    assert opened == [path.resolve().as_uri()]
    monkeypatch.setenv("INTERACTIVE_PIPE_SNAPSHOT", str(tmp_path / "shots/"))
    pipe.graph_representation(tmp_path / "g.html", view=True)
    assert len(opened) == 1


def test_graphviz_format_is_optional(pipe, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "graphviz", None)  # not installed
    assert pipe.graph_representation(tmp_path / "graph.svg") is None
    assert pipe.graph_representation(tmp_path / "graph", format="pdf") is None
    assert not list(tmp_path.iterdir())


def test_graphviz_digraph_uses_the_same_edges(pipe, tmp_path, monkeypatch):
    graphviz = pytest.importorskip("graphviz")
    monkeypatch.setattr(graphviz.Digraph, "render", lambda self, *args, **kwargs: None)
    dot = pipe.graph_representation(tmp_path / "graph.png")
    graph = pipeline_graph(pipe)
    ids = {node.id: f"node{idx}" for idx, node in enumerate(graph.nodes)}
    for source, target, label in EXPECTED_EDGES:
        assert f'{ids[source]} -> {ids[target]} [label="[{label}]"]' in dot.source


def test_graph_html_of_an_empty_pipeline():
    def gh_identity(img):
        return img

    pipe = interactive_pipeline(gui=None)(gh_identity)
    text = graph_html(pipe)
    assert 'data-src="in:img" data-dst="out:0"' in text


def test_gui_display_graph_writes_html(tmp_path, monkeypatch):
    from interactive_pipe.graphical.gui import InteractivePipeGUI

    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    monkeypatch.delenv("INTERACTIVE_PIPE_SNAPSHOT", raising=False)
    monkeypatch.chdir(tmp_path)
    messages = []
    gui = InteractivePipeGUI.__new__(InteractivePipeGUI)
    gui.pipeline = interactive_pipeline(gui=None)(gh_pipeline)
    gui.name = "Graph demo"
    gui.print_message = messages.append
    gui.display_graph()
    written = tmp_path / "Graph_demo_graph.html"
    assert written.exists()
    assert opened == [written.resolve().as_uri()]
    assert messages == [[f"Pipeline graph written to {written.resolve()}"]]
    assert "graphviz" not in str(messages).lower()
