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
    commands = {
        "python reference": [
            sys.executable,
            "conformance/run-python-events-reports-limits.py",
        ],
        "TypeScript reference": [
            "node",
            "--import=tsx",
            "conformance/run-typescript-events-reports-limits.mts",
        ],
        "python production": [
            sys.executable,
            "conformance/run-python-events-reports-limits-production.py",
        ],
        "TypeScript production": [
            "node",
            "--import=tsx",
            "conformance/run-typescript-events-reports-limits-production.mts",
        ],
    }
    snapshots = {name: _run(command) for name, command in commands.items()}
    accepted = snapshots["python reference"]
    for name, snapshot in snapshots.items():
        if snapshot != accepted:
            raise AssertionError(f"{name} events/reports/limits snapshot differs")
    fixture_count = len(json.loads(accepted)["fixtures"])
    print(f"Events, reports, and limits: {fixture_count} exact fixtures agree")


if __name__ == "__main__":
    main()
