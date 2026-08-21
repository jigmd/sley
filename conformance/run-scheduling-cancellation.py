from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _run(command: list[str]) -> bytes:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    return completed.stdout


def main() -> None:
    python_reference = _run(
        [sys.executable, "conformance/run-python-scheduling-cancellation.py"]
    )
    typescript_reference = _run(
        [
            "node",
            "--import=tsx",
            "conformance/run-typescript-scheduling-cancellation.mts",
        ]
    )
    if python_reference != typescript_reference:
        raise AssertionError("scheduling/cancellation reference snapshots differ")

    python_production = _run(
        [
            sys.executable,
            "conformance/run-python-scheduling-cancellation-production.py",
        ]
    )
    typescript_production = _run(
        [
            "node",
            "--import=tsx",
            "conformance/run-typescript-scheduling-cancellation-production.mts",
        ]
    )
    if python_production != typescript_production:
        raise AssertionError("scheduling/cancellation production snapshots differ")
    if python_reference != python_production:
        raise AssertionError(
            "production scheduling/cancellation snapshot differs from the references"
        )
    fixture_count = len(json.loads(python_reference)["fixtures"])
    print(f"Scheduling and cancellation: {fixture_count} exact fixtures agree")


if __name__ == "__main__":
    main()
