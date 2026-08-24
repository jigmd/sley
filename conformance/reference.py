from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_fixture(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or set(document) != {
        "schema_version",
        "cases",
    }:
        raise ValueError("invalid conformance document")
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    ids: set[str] = set()
    for case in cases:
        if set(case) != {"id", "requirement", "expected"}:
            raise ValueError("invalid case record")
        if not isinstance(case["id"], str) or not case["id"]:
            raise ValueError("case id must be nonempty")
        if case["id"] in ids:
            raise ValueError(f"duplicate case id: {case['id']}")
        if not isinstance(case["requirement"], str) or not case["requirement"]:
            raise ValueError(f"case {case['id']} has no requirement")
        if not isinstance(case["expected"], dict):
            raise TypeError(f"case {case['id']} has no expected snapshot")
        ids.add(case["id"])
    return cases


if __name__ == "__main__":
    fixture = Path(sys.argv[1])
    print(
        json.dumps(
            [
                {"id": case["id"], "snapshot": case["expected"]}
                for case in load_fixture(fixture)
            ]
        )
    )
