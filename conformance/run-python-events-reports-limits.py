from __future__ import annotations

import json
from pathlib import Path

from events_reports_limits_reference import evaluate_events_reports_limits

ROOT = Path(__file__).parent.parent
FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "events-reports-limits.json"


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures = []
    for fixture in collection["fixtures"]:
        snapshot = evaluate_events_reports_limits(fixture["program"]["scenario"])
        if snapshot != fixture["expect"]:
            raise AssertionError(f"{fixture['id']} reference mismatch")
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
