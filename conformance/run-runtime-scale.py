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
    python_snapshot = _run([sys.executable, "conformance/run-python-runtime-scale.py"])
    typescript_snapshot = _run(
        ["node", "--import=tsx", "conformance/run-typescript-runtime-scale.mts"]
    )
    if python_snapshot != typescript_snapshot:
        raise AssertionError("runtime-scale production snapshots differ")
    fixture_count = len(json.loads(python_snapshot)["fixtures"])
    print(f"Runtime scale: {fixture_count} exact fixtures agree")


if __name__ == "__main__":
    main()
