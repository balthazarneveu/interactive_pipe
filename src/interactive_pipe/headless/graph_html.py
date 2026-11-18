"""Pipeline diagram as one standalone HTML page, without graphviz.

``pipeline_graph(pipeline)`` lists the nodes (inputs, filters, outputs) and the
edges (which buffer goes from which node to which); both the HTML page and the
optional graphviz rendering of ``HeadlessPipeline.graph_representation`` use it.

``graph_html(pipeline)`` lays the graph out in layers (inputs at the top,
outputs at the bottom, each filter one layer below the last node it reads
from), orders each layer to reduce crossings (barycenter sweeps), places the
nodes horizontally (least squares under a minimum separation), routes edges
spanning several layers through their own lanes, and returns one HTML page:
inline SVG, inline CSS (light and dark) and a few lines of JS for hover
highlighting. No dependency, no external URL.
"""

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union

if TYPE_CHECKING:
    from interactive_pipe.headless.pipeline import HeadlessPipeline

# ---------------------------------------------------------------------------
# Graph structure
# ---------------------------------------------------------------------------


@dataclass
class GraphNode:
    id: str
    kind: str  # "input", "filter", "output"
    name: str
    lines: List[Tuple[str, str]] = field(default_factory=list)  # filter parameters: (main text, muted detail)
    doc: Optional[str] = None


@dataclass
class GraphEdge:
    source: str
    target: str
    label: str  # buffer name


@dataclass
class PipelineGraph:
    name: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]


def _flat_outputs(outputs: Any) -> List[Any]:
    flat = []
    for item in outputs or []:
        row = item if isinstance(item, (list, tuple)) else [item]
        flat.extend(out for out in row if out is not None)
    return flat


def _short(text: str, limit: int = 32) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parameter_lines(pipeline: "HeadlessPipeline", filt: Any) -> List[Tuple[str, str]]:
    from interactive_pipe.headless.describe import describe_control
    from interactive_pipe.headless.snapshot import format_value

    controls: Dict[str, Dict[str, Any]] = {}
    for ctrl in getattr(pipeline, "controls", None) or []:
        for target, param_name in getattr(ctrl, "targets", []):
            if target is filt:
                controls[param_name] = describe_control(ctrl)
    lines = []
    for param_name, value in filt.values.items():
        entry = controls.get(param_name)
        main = f"{param_name} = {_short(format_value(value), 24)}"
        if entry is None:
            lines.append((main, "fixed"))
            continue
        if "range" in entry:
            low, high = entry["range"][0], entry["range"][1]
            detail = f"[{format_value(low)}, {format_value(high)}]"
        elif "choices" in entry:
            detail = "{" + ", ".join(str(choice) for choice in entry["choices"]) + "}"
        else:
            detail = entry["kind"]
        if entry["name"] != param_name:
            detail = f"{entry['name']} {detail}"
        lines.append((main, _short(detail, 28)))
    return lines


def pipeline_graph(pipeline: "HeadlessPipeline") -> PipelineGraph:
    """Nodes and edges of a pipeline: the information drawn by ``graph_representation``.

    An edge goes from the last node that produced a buffer (an input, or the
    last filter before the consumer writing it) to each filter reading it and
    to each output showing it.
    """
    from interactive_pipe.headless.describe import _doc_line

    inputs = list(pipeline.inputs_routing or [])
    filters = list(pipeline.filters)
    nodes: List[GraphNode] = [GraphNode(f"in:{inp}", "input", str(inp)) for inp in inputs]
    for idx, filt in enumerate(filters):
        nodes.append(
            GraphNode(
                f"filter:{idx}",
                "filter",
                str(filt.name),
                _parameter_lines(pipeline, filt),
                _doc_line(getattr(filt, "apply", None)),
            )
        )

    def producer(buffer: Any, before: int) -> Optional[str]:
        found = f"in:{buffer}" if buffer in inputs else None
        for prev_idx in range(before):
            if buffer in (filters[prev_idx].outputs or []):
                found = f"filter:{prev_idx}"
        return found

    edges: List[GraphEdge] = []
    seen = set()

    def add_edge(source: Optional[str], target: str, buffer: Any):
        key = (source, target, str(buffer))
        if source is not None and key not in seen:
            seen.add(key)
            edges.append(GraphEdge(source, target, str(buffer)))

    for idx, filt in enumerate(filters):
        for buffer in filt.inputs or []:
            add_edge(producer(buffer, idx), f"filter:{idx}", buffer)
    for out_idx, out in enumerate(_flat_outputs(pipeline.outputs)):
        nodes.append(GraphNode(f"out:{out_idx}", "output", str(out)))
        add_edge(producer(out, len(filters)), f"out:{out_idx}", out)
    return PipelineGraph(str(pipeline.name) if pipeline.name else "pipeline", nodes, edges)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

CHAR_WIDTH = {"title": 0.62 * 13, "line": 0.62 * 11.5, "label": 0.62 * 11}
NODE_PAD = 12
TITLE_HEIGHT = 30
LINE_HEIGHT = 17
IO_HEIGHT = 30
LABEL_HEIGHT = 16
LAYER_GAP = 70
NODE_GAP = 28
LANE_GAP = 12
LANE_WIDTH = 8
MARGIN = 24


@dataclass
class _Box:
    id: str
    kind: str  # input, filter, output, dummy
    width: float
    height: float
    layer: int = 0
    x: float = 0.0  # center
    y: float = 0.0  # top


def _pav(targets: List[float]) -> List[float]:
    """Isotonic (non-decreasing) least squares fit: pool adjacent violators."""
    blocks: List[List[float]] = []  # [mean, weight]
    for value in targets:
        blocks.append([value, 1.0])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            mean_b, weight_b = blocks.pop()
            mean_a, weight_a = blocks[-1]
            blocks[-1] = [(mean_a * weight_a + mean_b * weight_b) / (weight_a + weight_b), weight_a + weight_b]
    fitted: List[float] = []
    for mean, weight in blocks:
        fitted.extend([mean] * int(weight))
    return fitted


def _separation(left: _Box, right: _Box) -> float:
    gap = NODE_GAP if left.kind != "dummy" and right.kind != "dummy" else LANE_GAP
    return (left.width + right.width) / 2 + gap


def _place(layer: List[_Box], desired: List[float]) -> None:
    """Centers closest to ``desired`` keeping the order and the minimum separation."""
    offsets = [0.0]
    for left, right in zip(layer, layer[1:]):
        offsets.append(offsets[-1] + _separation(left, right))
    fitted = _pav([want - off for want, off in zip(desired, offsets)])
    for box, value, off in zip(layer, fitted, offsets):
        box.x = value + off


def _crossings(upper: List[str], lower: List[str], links: Dict[str, List[str]]) -> int:
    pos_up = {node: idx for idx, node in enumerate(upper)}
    pairs = [(pos_up[src], idx) for idx, node in enumerate(lower) for src in links.get(node, []) if src in pos_up]
    count = 0
    for i, (a_up, a_low) in enumerate(pairs):
        for b_up, b_low in pairs[i + 1 :]:
            if (a_up - b_up) * (a_low - b_low) < 0:
                count += 1
    return count


@dataclass
class _Layout:
    boxes: Dict[str, _Box]
    routes: List[Tuple[GraphEdge, List[str]]]  # edge, chain of box ids (source, dummies..., target)
    width: float
    height: float


def _node_size(node: GraphNode, out_labels: List[str]) -> Tuple[float, float]:
    label_width = sum(len(label) * CHAR_WIDTH["label"] + 14 for label in out_labels) + 6 * max(len(out_labels) - 1, 0)
    if node.kind == "filter":
        text_width = len(node.name) * CHAR_WIDTH["title"]
        for main, detail in node.lines:
            text_width = max(text_width, (len(main) + 2 + len(detail)) * CHAR_WIDTH["line"])
        width = max(120.0, text_width + 2 * NODE_PAD, label_width + 2 * NODE_PAD)
        height = TITLE_HEIGHT + (len(node.lines) * LINE_HEIGHT + 8 if node.lines else 0)
        return width, height
    return max(70.0, len(node.name) * CHAR_WIDTH["title"] + 2 * NODE_PAD + 16, label_width), float(IO_HEIGHT)


def _out_labels(graph: PipelineGraph, node: GraphNode) -> List[str]:
    if node.kind != "filter":
        return []
    labels: List[str] = []
    for edge in graph.edges:
        if edge.source == node.id and edge.label not in labels:
            labels.append(edge.label)
    return labels


def layout_graph(graph: PipelineGraph) -> _Layout:
    """Layered layout: returns the boxes (center x, top y) and the edge routes."""
    preds: Dict[str, List[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        preds[edge.target].append(edge.source)

    # layers: inputs 0, a filter one below its lowest predecessor, outputs at the bottom
    layer_of: Dict[str, int] = {}
    for node in graph.nodes:
        if node.kind == "input":
            layer_of[node.id] = 0
        elif node.kind == "filter":  # filters come in execution order: predecessors are known
            layer_of[node.id] = 1 + max((layer_of.get(src, 0) for src in preds[node.id]), default=0)
    last = max((layer_of[n.id] for n in graph.nodes if n.kind == "filter"), default=0) + 1
    for node in graph.nodes:
        if node.kind == "output":
            layer_of[node.id] = last
    n_layers = last + 1

    boxes: Dict[str, _Box] = {}
    for node in graph.nodes:
        width, height = _node_size(node, _out_labels(graph, node))
        boxes[node.id] = _Box(node.id, node.kind, width, height, layer_of[node.id])

    # long edges go through one dummy box per crossed layer
    routes: List[Tuple[GraphEdge, List[str]]] = []
    for edge_idx, edge in enumerate(graph.edges):
        chain = [edge.source]
        for layer in range(layer_of[edge.source] + 1, layer_of[edge.target]):
            dummy_id = f"dummy:{edge_idx}:{layer}"
            boxes[dummy_id] = _Box(dummy_id, "dummy", LANE_WIDTH, 0.0, layer)
            chain.append(dummy_id)
        chain.append(edge.target)
        routes.append((edge, chain))
    up: Dict[str, List[str]] = {box_id: [] for box_id in boxes}
    down: Dict[str, List[str]] = {box_id: [] for box_id in boxes}
    for _edge, chain in routes:
        for src, dst in zip(chain, chain[1:]):
            up[dst].append(src)
            down[src].append(dst)

    # order within layers: barycenter sweeps, keep the order with the fewest crossings
    layers: List[List[str]] = [[] for _ in range(n_layers)]
    for box_id in boxes:  # insertion order: inputs, filters (execution order), outputs, dummies
        layers[boxes[box_id].layer].append(box_id)

    def total_crossings(order: List[List[str]]) -> int:
        return sum(_crossings(order[i], order[i + 1], up) for i in range(n_layers - 1))

    best = [list(layer) for layer in layers]
    best_count = total_crossings(best)
    current = [list(layer) for layer in layers]
    for sweep in range(12):
        downward = sweep % 2 == 0
        indexes = range(1, n_layers) if downward else range(n_layers - 2, -1, -1)
        for layer_idx in indexes:
            ref = current[layer_idx - 1] if downward else current[layer_idx + 1]
            pos = {box_id: idx for idx, box_id in enumerate(ref)}
            links = up if downward else down
            keys = {}
            for idx, box_id in enumerate(current[layer_idx]):
                linked = [pos[other] for other in links[box_id] if other in pos]
                keys[box_id] = sum(linked) / len(linked) if linked else float(idx)
            current[layer_idx].sort(key=lambda box_id: keys[box_id])
        count = total_crossings(current)
        if count < best_count:
            best, best_count = [list(layer) for layer in current], count
    layers = best

    # horizontal placement: pack, then pull each node toward its neighbours
    for layer in layers:
        position = 0.0
        for idx, box_id in enumerate(layer):
            if idx:
                position += _separation(boxes[layer[idx - 1]], boxes[box_id])
            boxes[box_id].x = position
        shift = position / 2
        for box_id in layer:
            boxes[box_id].x -= shift
    for sweep in range(16):
        downward = sweep % 2 == 0
        indexes = range(1, n_layers) if downward else range(n_layers - 2, -1, -1)
        links = up if downward else down
        for layer_idx in indexes:
            layer_boxes = [boxes[box_id] for box_id in layers[layer_idx]]
            desired = []
            for box in layer_boxes:
                linked = [boxes[other].x for other in links[box.id]]
                desired.append(sum(linked) / len(linked) if linked else box.x)
            _place(layer_boxes, desired)
    # final pass: nodes with links both ways sit between them
    for layer_idx in range(1, n_layers - 1):
        layer_boxes = [boxes[box_id] for box_id in layers[layer_idx]]
        desired = []
        for box in layer_boxes:
            linked = [boxes[other].x for other in up[box.id] + down[box.id]]
            desired.append(sum(linked) / len(linked) if linked else box.x)
        _place(layer_boxes, desired)

    # straighten long edges: one x for all the dummies of a chain when it fits between the neighbours
    position_in_layer = {box_id: idx for layer in layers for idx, box_id in enumerate(layer)}

    def fits(box_id: str, x: float) -> bool:
        box, layer = boxes[box_id], layers[boxes[box_id].layer]
        idx = position_in_layer[box_id]
        if idx > 0 and x - boxes[layer[idx - 1]].x < _separation(boxes[layer[idx - 1]], box) - 1e-6:
            return False
        if idx + 1 < len(layer) and boxes[layer[idx + 1]].x - x < _separation(box, boxes[layer[idx + 1]]) - 1e-6:
            return False
        return True

    for _sweep in range(2):
        for _edge, chain in routes:
            dummies = chain[1:-1]
            if not dummies:
                continue
            xs = sorted(boxes[box_id].x for box_id in dummies)
            ends = [boxes[chain[0]].x, boxes[chain[-1]].x]
            for candidate in [xs[len(xs) // 2], *ends, *xs]:
                if all(fits(box_id, candidate) for box_id in dummies):
                    for box_id in dummies:
                        boxes[box_id].x = candidate
                    break

    # vertical placement: layers stacked, nodes centered in their layer
    top = MARGIN
    for layer in layers:
        if not layer:  # no input (generator pipelines)
            continue
        height = max(boxes[box_id].height for box_id in layer)
        for box_id in layer:
            box = boxes[box_id]
            box.y = top + (height - box.height) / 2
            if box.kind == "dummy":
                box.y, box.height = top, height
        top += height + LAYER_GAP
    left = min(box.x - box.width / 2 for box in boxes.values())
    right = max(box.x + box.width / 2 for box in boxes.values())
    for box in boxes.values():
        box.x += MARGIN - left
    return _Layout(boxes, routes, right - left + 2 * MARGIN, top - LAYER_GAP + MARGIN)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f7f7f5; --fg: #1f2328; --muted: #6a7078; --faint: #9aa0a6;
  --filter-bg: #ffffff; --filter-stroke: #4b6bfb; --filter-head: #e9edff;
  --io-bg: #f0f0ee; --io-stroke: #8a8f98;
  --edge: #8a8f98; --label-bg: #f7f7f5; --hi: #e8590c;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #17181b; --fg: #e6e6e6; --muted: #a0a6ad; --faint: #6f757c;
    --filter-bg: #22252b; --filter-stroke: #7d93ff; --filter-head: #2c3350;
    --io-bg: #1e2024; --io-stroke: #7a8088;
    --edge: #7a8088; --label-bg: #17181b; --hi: #ff922b;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header { padding: 16px 16px 4px; }
h1 { margin: 0; font-size: 18px; font-weight: 600; }
header p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.scroll { overflow: auto; padding: 8px 0 16px; }
svg { display: block; margin: 0 auto; }
svg text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "DejaVu Sans Mono", monospace; fill: var(--fg); }
.filter rect.box { fill: var(--filter-bg); }
.filter rect.outline { fill: none; stroke: var(--filter-stroke); stroke-width: 1.5; }
.filter rect.head { fill: var(--filter-head); }
.filter line.sep { stroke: var(--filter-stroke); stroke-width: 1; opacity: .5; }
.filter text.title { font-size: 13px; font-weight: 700; }
.filter text.param { font-size: 11.5px; }
.filter tspan.detail { fill: var(--muted); }
.filter tspan.fixed { fill: var(--faint); }
.io rect { fill: var(--io-bg); stroke: var(--io-stroke); stroke-width: 1.2; stroke-dasharray: 4 3; }
.io text { font-size: 12.5px; }
.io text.tag { font-size: 9.5px; fill: var(--muted); letter-spacing: .06em; }
.edge path { fill: none; stroke: var(--edge); stroke-width: 1.4; }
.edge-label rect { fill: var(--label-bg); stroke: var(--edge); stroke-width: .8; }
.edge-label text { font-size: 11px; fill: var(--muted); }
#arrow path { fill: var(--edge); }
#arrow-hi path { fill: var(--hi); }
.node { cursor: default; }
svg.focus .node, svg.focus .edge, svg.focus .edge-label { opacity: .25; }
svg.focus .hi { opacity: 1; }
svg.focus .edge.hi path { stroke: var(--hi); stroke-width: 2; }
svg.focus .node.hi rect.outline, svg.focus .node.hi.io rect { stroke: var(--hi); }
"""

_JS = """
(function () {
  var svg = document.querySelector("svg.pipeline");
  if (!svg) return;
  function linked(id) {
    return svg.querySelectorAll('[data-src="' + id + '"], [data-dst="' + id + '"]');
  }
  svg.querySelectorAll(".node").forEach(function (node) {
    node.addEventListener("mouseenter", function () {
      var id = node.getAttribute("data-id");
      svg.classList.add("focus");
      node.classList.add("hi");
      linked(id).forEach(function (el) {
        el.classList.add("hi");
        if (el.classList.contains("edge")) {
          el.querySelector("path").setAttribute("marker-end", "url(#arrow-hi)");
          [el.getAttribute("data-src"), el.getAttribute("data-dst")].forEach(function (other) {
            var n = svg.querySelector('.node[data-id="' + other + '"]');
            if (n) n.classList.add("hi");
          });
        }
      });
    });
    node.addEventListener("mouseleave", function () {
      svg.classList.remove("focus");
      svg.querySelectorAll(".hi").forEach(function (el) { el.classList.remove("hi"); });
      svg.querySelectorAll(".edge path").forEach(function (p) { p.setAttribute("marker-end", "url(#arrow)"); });
    });
  });
})();
"""


def _num(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _spread(center: float, widths: Sequence[float], gap: float) -> List[float]:
    total = sum(widths) + gap * max(len(widths) - 1, 0)
    position = center - total / 2
    centers = []
    for width in widths:
        centers.append(position + width / 2)
        position += width + gap
    return centers


def _render_svg(graph: PipelineGraph, layout: _Layout) -> str:
    boxes = layout.boxes
    nodes = {node.id: node for node in graph.nodes}
    esc = html.escape

    # ports: one per buffer leaving a node (fan-out shares it), one per edge entering a node
    def next_x(chain: List[str], index: int) -> float:
        return boxes[chain[index]].x

    out_port: Dict[Tuple[str, str], float] = {}
    label_pos: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for node in graph.nodes:
        groups: Dict[str, List[float]] = {}
        for edge, chain in layout.routes:
            if edge.source == node.id:
                groups.setdefault(edge.label, []).append(next_x(chain, 1))
        if not groups:
            continue
        labels = sorted(groups, key=lambda label: sum(groups[label]) / len(groups[label]))
        box = boxes[node.id]
        widths = [len(label) * CHAR_WIDTH["label"] + 14 for label in labels]
        if node.kind == "filter":
            centers = _spread(box.x, widths, 6)
        else:
            centers = _spread(box.x, [10.0] * len(labels), 6)
        for label, x in zip(labels, centers):
            out_port[(node.id, label)] = x
            label_pos[(node.id, label)] = (x, box.y + box.height + 4 + LABEL_HEIGHT / 2)
    in_port: Dict[int, float] = {}
    for node in graph.nodes:
        entering = [(idx, chain) for idx, (edge, chain) in enumerate(layout.routes) if edge.target == node.id]
        entering.sort(key=lambda item: boxes[item[1][-2]].x)
        box = boxes[node.id]
        step = min(14.0, (box.width - 16) / max(len(entering) - 1, 1))
        for rank, (idx, _chain) in enumerate(entering):
            in_port[idx] = box.x + (rank - (len(entering) - 1) / 2) * step

    parts: List[str] = []
    width, height = layout.width, layout.height
    parts.append(
        f'<svg class="pipeline" width="{_num(width)}" height="{_num(height)}" '
        f'viewBox="0 0 {_num(width)} {_num(height)}" role="img" aria-label="{esc(graph.name)} pipeline graph">'
    )
    parts.append(
        "<defs>"
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        '<path d="M0,0 L10,5 L0,10 z"/></marker>'
        '<marker id="arrow-hi" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        '<path d="M0,0 L10,5 L0,10 z"/></marker>'
        "</defs>"
    )

    # edges
    parts.append('<g class="edges">')
    for idx, (edge, chain) in enumerate(layout.routes):
        src, dst = boxes[chain[0]], boxes[chain[-1]]
        has_label = nodes[edge.source].kind == "filter"
        start_y = src.y + src.height + (LABEL_HEIGHT + 4 if has_label else 0)
        points: List[Tuple[float, float]] = [(out_port[(edge.source, edge.label)], start_y)]
        for dummy_id in chain[1:-1]:
            dummy = boxes[dummy_id]
            points.append((dummy.x, dummy.y))
            points.append((dummy.x, dummy.y + dummy.height))
        points.append((in_port[idx], dst.y - 1))
        path = [f"M{_num(points[0][0])},{_num(points[0][1])}"]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if abs(x1 - x0) < 0.5:
                path.append(f"L{_num(x1)},{_num(y1)}")
            else:
                mid = (y0 + y1) / 2
                path.append(f"C{_num(x0)},{_num(mid)} {_num(x1)},{_num(mid)} {_num(x1)},{_num(y1)}")
        title = f"{nodes[edge.source].name} → {nodes[edge.target].name} [{edge.label}]"
        parts.append(
            f'<g class="edge" data-src="{esc(edge.source)}" data-dst="{esc(edge.target)}" '
            f'data-label="{esc(edge.label)}"><title>{esc(title)}</title>'
            f'<path d="{" ".join(path)}" marker-end="url(#arrow)"/></g>'
        )
    parts.append("</g>")

    # buffer labels under the filter producing them
    parts.append('<g class="labels">')
    for (source, label), (x, y) in label_pos.items():
        if nodes[source].kind != "filter":
            continue
        label_width = len(label) * CHAR_WIDTH["label"] + 14
        parts.append(
            f'<g class="edge-label" data-src="{esc(source)}">'
            f'<rect x="{_num(x - label_width / 2)}" y="{_num(y - LABEL_HEIGHT / 2)}" width="{_num(label_width)}" '
            f'height="{LABEL_HEIGHT}" rx="8"/>'
            f'<text x="{_num(x)}" y="{_num(y)}" text-anchor="middle" dominant-baseline="central">'
            f"{esc(label)}</text></g>"
        )
    parts.append("</g>")

    # nodes
    parts.append('<g class="nodes">')
    for node in graph.nodes:
        box = boxes[node.id]
        left = box.x - box.width / 2
        attrs = f'data-id="{esc(node.id)}" data-name="{esc(node.name)}"'
        if node.kind == "filter":
            tooltip = node.name + (f": {node.doc}" if node.doc else "")
            parts.append(f'<g class="node filter" {attrs}><title>{esc(tooltip)}</title>')
            parts.append(
                f'<rect class="box" x="{_num(left)}" y="{_num(box.y)}" width="{_num(box.width)}" '
                f'height="{_num(box.height)}" rx="6"/>'
            )
            if node.lines:
                clip_id = "clip-" + node.id.replace(":", "-")
                parts.append(
                    f'<clipPath id="{clip_id}"><rect x="{_num(left)}" y="{_num(box.y)}" '
                    f'width="{_num(box.width)}" height="{_num(box.height)}" rx="6"/></clipPath>'
                )
                parts.append(
                    f'<rect class="head" x="{_num(left)}" y="{_num(box.y)}" width="{_num(box.width)}" '
                    f'height="{TITLE_HEIGHT}" clip-path="url(#{clip_id})"/>'
                )
                parts.append(
                    f'<line class="sep" x1="{_num(left)}" y1="{_num(box.y + TITLE_HEIGHT)}" '
                    f'x2="{_num(left + box.width)}" y2="{_num(box.y + TITLE_HEIGHT)}"/>'
                )
            parts.append(
                f'<rect class="outline" x="{_num(left)}" y="{_num(box.y)}" width="{_num(box.width)}" '
                f'height="{_num(box.height)}" rx="6"/>'
            )
            parts.append(
                f'<text class="title" x="{_num(box.x)}" y="{_num(box.y + TITLE_HEIGHT / 2)}" text-anchor="middle" '
                f'dominant-baseline="central">{esc(node.name)}</text>'
            )
            for line_idx, (main, detail) in enumerate(node.lines):
                y = box.y + TITLE_HEIGHT + 4 + LINE_HEIGHT * (line_idx + 0.5)
                css = "fixed" if detail == "fixed" else "detail"
                parts.append(
                    f'<text class="param" x="{_num(left + NODE_PAD)}" y="{_num(y)}" dominant-baseline="central">'
                    f'{esc(main)}<tspan class="{css}" dx="8">{esc(detail)}</tspan></text>'
                )
            parts.append("</g>")
        else:
            tag = "INPUT" if node.kind == "input" else "OUTPUT"
            parts.append(f'<g class="node io {node.kind}" {attrs}><title>{tag.lower()} {esc(node.name)}</title>')
            parts.append(
                f'<rect x="{_num(left)}" y="{_num(box.y)}" width="{_num(box.width)}" height="{_num(box.height)}" '
                f'rx="{_num(box.height / 2)}"/>'
            )
            parts.append(
                f'<text x="{_num(box.x)}" y="{_num(box.y + box.height / 2)}" text-anchor="middle" '
                f'dominant-baseline="central">{esc(node.name)}</text>'
            )
            parts.append("</g>")
    parts.append("</g></svg>")
    return "".join(parts)


def graph_html(pipeline: Union["HeadlessPipeline", PipelineGraph]) -> str:
    """The pipeline diagram as a standalone HTML page (a string)."""
    graph = pipeline if isinstance(pipeline, PipelineGraph) else pipeline_graph(pipeline)
    layout = layout_graph(graph)
    n_filters = sum(node.kind == "filter" for node in graph.nodes)
    n_inputs = sum(node.kind == "input" for node in graph.nodes)
    n_outputs = sum(node.kind == "output" for node in graph.nodes)
    title = html.escape(graph.name)
    counts = (
        f"{n_inputs} input{'s' * (n_inputs != 1)} · {n_filters} filter{'s' * (n_filters != 1)} "
        f"· {n_outputs} output{'s' * (n_outputs != 1)} · hover a node to highlight its connections"
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title} pipeline</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        f"<header><h1>{title}</h1><p>{counts}</p></header>\n"
        f'<div class="scroll">{_render_svg(graph, layout)}</div>\n'
        f"<script>{_JS}</script>\n</body>\n</html>\n"
    )


def write_graph_html(pipeline: "HeadlessPipeline", path: Union[str, Path]) -> Path:
    """Write the diagram of ``pipeline`` to ``path`` (an ``.html`` file); returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph_html(pipeline), encoding="utf-8")
    return path
