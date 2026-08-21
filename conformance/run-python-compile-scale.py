from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import Flow, node

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "compile-scale.json"


def _handler(_context: object) -> None:
    pass


def _run(fixture: dict[str, Any]) -> dict[str, int]:
    size = fixture["size"]
    if fixture["kind"] == "node_chain":
        nodes = [node(_handler, name=f"node-{index}") for index in range(size)]
        for index in range(size - 1):
            nodes[index].link(nodes[index + 1])
        root = Flow(nodes[0], name="root")
    elif fixture["kind"] == "nested_flows":
        entry = node(_handler, name="leaf")
        for index in range(size):
            entry = Flow(entry, name=f"nested-{index}")
        root = Flow(entry, name="root")
    else:
        raise AssertionError(f"unknown compile-scale kind {fixture['kind']}")

    description = root.compile().describe()
    return {
        "elements": len(description["elements"]),
        "scopes": len(description["scope_definitions"]),
        "last_element_id": description["elements"][-1]["element_id"],
    }


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    observed: list[dict[str, Any]] = []
    for fixture in collection["fixtures"]:
        snapshot = _run(fixture)
        if snapshot != fixture["expect"]:
            raise AssertionError(
                f"{fixture['id']} mismatch: expected={fixture['expect']}, actual={snapshot}"
            )
        observed.append({"id": fixture["id"], "snapshot": snapshot})
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": observed},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
