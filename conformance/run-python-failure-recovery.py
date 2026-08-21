from __future__ import annotations

import json
from pathlib import Path

from failure_recovery_reference import evaluate_failure_recovery

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "fixtures" / "failure-recovery.json"


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if collection.get("schema_version") != 1:
        raise AssertionError("unsupported failure fixture schema")
    observed: list[dict[str, object]] = []
    fixture_ids: set[str] = set()
    for fixture in collection["fixtures"]:
        fixture_id = fixture["id"]
        if fixture_id in fixture_ids:
            raise AssertionError(f"duplicate fixture ID {fixture_id}")
        fixture_ids.add(fixture_id)
        actual = evaluate_failure_recovery(fixture["program"])
        if actual != fixture["expect"]:
            raise AssertionError(
                f"{fixture_id} mismatch\n"
                f"expected={json.dumps(fixture['expect'], indent=2, sort_keys=True)}\n"
                f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
            )
        observed.append({"id": fixture_id, "snapshot": actual})
    print(
        json.dumps(
            {"schema_version": 1, "fixtures": observed},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
