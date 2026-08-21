from __future__ import annotations

import json
from pathlib import Path

from scheduling_cancellation_reference import evaluate_scheduling_cancellation

ROOT = Path(__file__).parent.parent
FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "scheduling-cancellation.json"


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = []
    for fixture in collection["fixtures"]:
        snapshot = evaluate_scheduling_cancellation(fixture["program"])
        if snapshot != fixture["expect"]:
            raise AssertionError(
                f"{fixture['id']} reference mismatch\n"
                f"expected={fixture['expect']!r}\nactual={snapshot!r}"
            )
        fixtures.append({"id": fixture["id"], "snapshot": snapshot})
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": fixtures},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
