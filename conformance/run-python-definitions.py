from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import Flow, GraphElement, RetryPolicy, node

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "definitions.json"


def _handler(name: str):
    def callback(_context: object) -> None:
        pass

    callback.__name__ = name
    return callback


def _snapshot(fixture: dict[str, Any]) -> dict[str, Any]:
    elements: dict[str, GraphElement[Any]] = {}
    nodes: list[tuple[str, Any]] = []
    for definition in fixture["nodes"]:
        options = definition.get("options", {})
        retry_options = options.get("retry", {})
        retry = RetryPolicy(
            max_attempts=retry_options.get("max_attempts", 1),
            delay_ms=retry_options.get("delay_ms", 0),
        )
        occurrence = node(
            _handler(definition["handler_name"]),
            name=options.get("name"),
            retry=retry,
            timeout_ms=options.get("timeout_ms"),
        )
        elements[definition["id"]] = occurrence
        nodes.append((definition["id"], occurrence))

    flow_definition = fixture["flow"]
    flow = Flow(
        elements[flow_definition["entry"]],
        name=flow_definition.get("name"),
        exits=flow_definition.get("exits", ()),
        concurrency=flow_definition.get("concurrency", 1),
        max_activations=flow_definition.get("max_activations"),
    )
    elements["$flow"] = flow

    for link in fixture["links"]:
        source = elements[link["source"]]
        target = elements[link["target"]]
        if "action" in link:
            source.link(target, link["action"])
        else:
            source.link(target)

    ids = {element: identifier for identifier, element in elements.items()}

    def links(element: GraphElement[Any]) -> list[dict[str, Any]]:
        return [
            {"action": link.action, "target": ids[link.target]}
            for link in element.links()
        ]

    return {
        "nodes": [
            {
                "id": identifier,
                "name": occurrence.name,
                "retry": {
                    "max_attempts": occurrence.retry.max_attempts,
                    "delay_ms": occurrence.retry.delay_ms,
                },
                "timeout_ms": occurrence.timeout_ms,
                "links": links(occurrence),
            }
            for identifier, occurrence in nodes
        ],
        "flow": {
            "name": flow.name,
            "entry": ids[flow.entry],
            "exits": list(flow.exits),
            "concurrency": flow.concurrency,
            "max_activations": flow.max_activations,
            "links": links(flow),
        },
    }


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed: list[dict[str, Any]] = []
    for fixture in collection["fixtures"]:
        actual = _snapshot(fixture)
        if actual != fixture["expect"]:
            raise AssertionError(
                f"{fixture['id']} mismatch\n"
                f"expected={json.dumps(fixture['expect'], indent=2, sort_keys=True)}\n"
                f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
            )
        observed.append({"id": fixture["id"], "snapshot": actual})
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": observed},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
