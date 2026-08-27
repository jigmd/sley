import argparse
import html
import importlib
import json
import re
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sley import Flow


def flow_to_json(flow):
    """Convert Sley's compiled description into display data."""
    description = flow.compile().describe()
    elements = description["elements"]

    nodes = [
        {
            "id": element["element_id"],
            "name": element["name"],
        }
        for element in elements
        if element["kind"] == "node"
    ]
    flows = [
        {
            "id": element["element_id"],
            "name": element["name"],
        }
        for element in elements
        if element["kind"] == "flow"
    ]
    links = [
        {
            "source": element["element_id"],
            "target": link["target_element_id"],
            "action": link["action"] or "unlabelled",
        }
        for element in elements
        for link in element["links"]
    ]
    entry_links = [
        {
            "source": scope["owner_element_id"],
            "target": scope["entry_element_id"],
            "action": "entry",
        }
        for scope in description["scopes"]
    ]
    return {"nodes": nodes, "flows": flows, "links": entry_links + links}


def build_mermaid(flow):
    data = flow_to_json(flow)
    lines = ["flowchart LR"]
    for element in data["flows"] + data["nodes"]:
        shape = "{{" if element in data["flows"] else "["
        close = "}}" if element in data["flows"] else "]"
        lines.append(f"    E{element['id']}{shape}{element['name']}{close}")
    for link in data["links"]:
        lines.append(f"    E{link['source']} -->|{link['action']}| E{link['target']}")
    return "\n".join(lines)


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <script src="https://d3js.org/d3.v7.min.js"></script>
  <style>
    body { margin: 0; font: 14px system-ui, sans-serif; }
    svg { width: 100vw; height: 100vh; }
    line { stroke: #8a8a8a; stroke-width: 1.5; }
    circle { stroke: white; stroke-width: 2; }
    text { pointer-events: none; }
    .edge-label { fill: #555; font-size: 11px; }
  </style>
</head>
<body>
<svg></svg>
<script>
d3.json("__JSON__").then(data => {
  const nodes = [
    ...data.flows.map(node => ({...node, kind: "flow"})),
    ...data.nodes.map(node => ({...node, kind: "node"})),
  ];
  const links = data.links.map(link => ({...link}));
  const svg = d3.select("svg");
  const width = window.innerWidth;
  const height = window.innerHeight;
  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(node => node.id).distance(120))
    .force("charge", d3.forceManyBody().strength(-450))
    .force("center", d3.forceCenter(width / 2, height / 2));

  const edges = svg.append("g").selectAll("line").data(links).join("line");
  const labels = svg.append("g").selectAll("text").data(links).join("text")
    .attr("class", "edge-label").text(link => link.action);
  const groups = svg.append("g").selectAll("g").data(nodes).join("g")
    .call(d3.drag()
      .on("start", (event, node) => { node.fx = event.x; node.fy = event.y; })
      .on("drag", (event, node) => { node.fx = event.x; node.fy = event.y; })
      .on("end", (_event, node) => { node.fx = null; node.fy = null; }));
  groups.append("circle").attr("r", node => node.kind === "flow" ? 24 : 16)
    .attr("fill", node => node.kind === "flow" ? "#d1495b" : "#00798c");
  groups.append("text").attr("x", 28).attr("y", 5).text(node => node.name);

  simulation.on("tick", () => {
    edges.attr("x1", link => link.source.x).attr("y1", link => link.source.y)
      .attr("x2", link => link.target.x).attr("y2", link => link.target.y);
    labels.attr("x", link => (link.source.x + link.target.x) / 2)
      .attr("y", link => (link.source.y + link.target.y) / 2);
    groups.attr("transform", node => `translate(${node.x},${node.y})`);
  });
});
</script>
</body>
</html>
"""


def create_d3_visualization(data, output_dir, filename, html_title):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{filename}.json"
    html_path = directory / f"{filename}.html"
    json_path.write_text(f"{json.dumps(data, indent=2)}\n", encoding="utf-8")
    html_path.write_text(
        HTML.replace("__TITLE__", html.escape(html_title)).replace(
            "__JSON__", json_path.name
        ),
        encoding="utf-8",
    )
    return str(html_path)


def serve_visualization(html_path, auto_open):
    path = Path(html_path).resolve()
    handler = partial(SimpleHTTPRequestHandler, directory=path.parent)
    server = ThreadingHTTPServer(("localhost", 0), handler)
    url = f"http://localhost:{server.server_port}/{path.name}"
    if auto_open:
        webbrowser.open(url)
    print(f"Serving visualization at {url}; press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nVisualization server stopped.")
    finally:
        server.server_close()


def visualize_flow(
    flow: Flow,
    flow_name: str,
    serve: bool = True,
    auto_open: bool = True,
    output_dir: str = "./viz",
    html_title: str | None = None,
):
    print(build_mermaid(flow))
    filename = re.sub(r"[^a-z0-9_-]+", "_", flow_name.lower()).strip("_")
    if not filename:
        raise ValueError("flow_name must contain a letter or number")
    html_path = create_d3_visualization(
        flow_to_json(flow), output_dir, filename, html_title or flow_name
    )
    print(f"Visualization created at {html_path}")
    if not serve:
        return html_path
    serve_visualization(html_path, auto_open)
    return html_path


def load_flow(module_name, variable):
    return getattr(importlib.import_module(module_name), variable)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="async_flow")
    parser.add_argument("--flow", default="order_pipeline")
    parser.add_argument("--name", default="Flow Visualization")
    parser.add_argument("--output-dir", default="./viz")
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    arguments = parser.parse_args()

    visualize_flow(
        load_flow(arguments.module, arguments.flow),
        arguments.name,
        serve=not arguments.no_serve,
        auto_open=not arguments.no_open,
        output_dir=arguments.output_dir,
    )
