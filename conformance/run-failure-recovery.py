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
        [sys.executable, "conformance/run-python-failure-recovery.py"]
    )
    typescript_reference = _run(
        ["node", "--import=tsx", "conformance/run-typescript-failure-recovery.mts"]
    )
    if python_reference != typescript_reference:
        raise AssertionError(
            "failure/recovery reference snapshots differ\n"
            f"python={python_reference.decode()}\n"
            f"typescript={typescript_reference.decode()}"
        )

    python_production = _run(
        [sys.executable, "conformance/run-python-failure-recovery-production.py"]
    )
    typescript_production = _run(
        [
            "node",
            "--import=tsx",
            "conformance/run-typescript-failure-recovery-production.mts",
        ]
    )
    if python_production != typescript_production:
        raise AssertionError(
            "failure/recovery production snapshots differ\n"
            f"python={python_production.decode()}\n"
            f"typescript={typescript_production.decode()}"
        )
    if python_reference != python_production:
        raise AssertionError(
            "production failure/recovery snapshot differs from the references\n"
            f"reference={python_reference.decode()}\n"
            f"production={python_production.decode()}"
        )
    fixture_count = len(json.loads(python_reference)["fixtures"])
    print(f"Failure and recovery: {fixture_count} exact fixtures agree")


if __name__ == "__main__":
    main()
