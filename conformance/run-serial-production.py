from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
FIXTURE_PATH = ROOT / "conformance" / "fixtures" / "serial.json"
IMPLEMENTED_FIXTURES = {
    "S01_implicit_default",
    "S02_explicit_input",
    "S03_hard_end",
    "S04_output_presence",
    "S05_fanout_combine",
    "S06_combine_replacement",
    "S07_declared_exit",
    "S08_unknown_action",
    "S09_nested_forwarding",
    "S11_state_copy",
    "S12_explicit_null_input",
    "S13_atomic_batch_rejection",
}


def _run(command: list[str]) -> bytes:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    return completed.stdout


def _expected() -> dict[str, object]:
    collection = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixtures: list[dict[str, Any]] = []
    for fixture in collection["fixtures"]:
        if fixture["id"] not in IMPLEMENTED_FIXTURES:
            continue
        record: dict[str, Any] = {
            "id": fixture["id"],
            "result": fixture["expect"]["result"],
        }
        if "initial_state_after" in fixture["expect"]:
            record["initial_state_after"] = fixture["expect"]["initial_state_after"]
        if fixture["id"] == "S08_unknown_action":
            record["run_projection"] = fixture["expect"]["run_projection"]
        if fixture["id"] == "S13_atomic_batch_rejection":
            record["stats"] = {
                key: value
                for key, value in fixture["expect"]["stats"].items()
                if key != "duration_ms"
            }
        fixtures.append(record)
    return {"fixtures": fixtures}


def main() -> None:
    python_snapshot = _run(
        [sys.executable, "conformance/run-python-serial-production.py"]
    )
    typescript_snapshot = _run(
        [
            "node",
            "--import=tsx",
            "conformance/run-typescript-serial-production.mts",
        ]
    )
    if python_snapshot != typescript_snapshot:
        raise AssertionError(
            "Python and TypeScript serial production snapshots differ\n"
            f"python={python_snapshot.decode()}\n"
            f"typescript={typescript_snapshot.decode()}"
        )
    actual = json.loads(python_snapshot)
    expected = _expected()
    if actual != expected:
        raise AssertionError(
            "serial production snapshot differs from the accepted fixture\n"
            f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
            f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
        )
    print(f"Serial execution: {len(actual['fixtures'])} exact fixtures agree")


if __name__ == "__main__":
    main()
