from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "python"))

from caskada import Flow, GraphElement, node

FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "serial.json"


def _handler(_context: object) -> None:
    pass


def _build(program: dict[str, Any]) -> Flow[Any]:
    definitions = program["elements"]
    elements: dict[str, GraphElement[Any]] = {
        identifier: node(_handler, name=identifier)
        for identifier, definition in definitions.items()
        if definition["kind"] == "node"
    }
    unresolved = {
        identifier: definition
        for identifier, definition in definitions.items()
        if definition["kind"] == "flow"
    }
    while unresolved:
        progressed = False
        for identifier, definition in tuple(unresolved.items()):
            entry = elements.get(definition["entry"])
            if entry is None:
                continue
            elements[identifier] = Flow(
                entry,
                name=identifier,
                exits=definition.get("exits", ()),
                concurrency=definition.get("concurrency", 1),
                max_activations=definition.get("max_activations"),
            )
            del unresolved[identifier]
            progressed = True
        if not progressed:
            raise AssertionError("fixture Flow entries contain an unresolved cycle")

    for link in program["links"]:
        source = elements[link["source"]]
        target = elements[link["target"]]
        if "action" in link:
            source.link(target, link["action"])
        else:
            source.link(target)
    root = elements[program["root"]]
    if type(root) is not Flow:
        raise AssertionError("fixture root must be a Flow")
    return root


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture = next(
        item for item in collection["fixtures"] if item["id"] == "S00_compile_nested"
    )
    actual = _build(fixture["program"]).compile().describe()
    expected = fixture["expect"]["compiled"]
    if actual != expected:
        raise AssertionError(
            "S00_compile_nested production mismatch\n"
            f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
            f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
        )
    print(json.dumps(actual, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
