from __future__ import annotations

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
    python_snapshot = _run([sys.executable, "conformance/run-python-compile.py"])
    typescript_snapshot = _run(
        ["node", "--import=tsx", "conformance/run-typescript-compile.mts"]
    )
    if python_snapshot != typescript_snapshot:
        raise AssertionError(
            "Python and TypeScript compiled descriptions differ\n"
            f"python={python_snapshot.decode()}\n"
            f"typescript={typescript_snapshot.decode()}"
        )
    print("Compilation: S00 exact description agrees across ports")


if __name__ == "__main__":
    main()
