from __future__ import annotations

import json
from pathlib import Path

from reference import ReferenceInterpreter

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "fixtures" / "serial.json"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def main() -> None:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if collection.get("schema_version") != 1:
        raise AssertionError("unsupported fixture schema")

    observed: list[dict[str, object]] = []
    fixture_ids: set[str] = set()
    for fixture in collection["fixtures"]:
        fixture_id = fixture["id"]
        if fixture_id in fixture_ids:
            raise AssertionError(f"duplicate fixture ID {fixture_id}")
        fixture_ids.add(fixture_id)

        actual = ReferenceInterpreter(fixture["program"]).run()
        selected = {key: actual[key] for key in fixture["expect"]}
        if selected != fixture["expect"]:
            raise AssertionError(
                f"{fixture_id} mismatch\n"
                f"expected={json.dumps(fixture['expect'], indent=2, sort_keys=True)}\n"
                f"actual={json.dumps(selected, indent=2, sort_keys=True)}"
            )
        observed.append({"id": fixture_id, "snapshot": selected})

    print(_canonical({"schema_version": 1, "fixtures": observed}))


if __name__ == "__main__":
    main()
