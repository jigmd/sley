from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from reference import load_fixture

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "conformance" / "fixtures" / "runtime.json"
BASELINE = ROOT / "architecture" / "v3-implementation-baseline.json"


def run_json(command: list[str]) -> list[dict[str, Any]]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, list):
        raise TypeError(f"adapter returned a non-list: {command[0]}")
    return value


def compare(
    name: str,
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{name} conformance mismatch\n"
            f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
            f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
        )


def verify_baseline() -> None:
    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    for group in ("authority", "verification_tools"):
        for record in document[group]:
            path = ROOT / record["path"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != record["sha256"]:
                raise AssertionError(f"baseline hash mismatch: {record['path']}")


def main() -> None:
    cases = load_fixture(FIXTURE)
    expected = [{"id": case["id"], "snapshot": case["expected"]} for case in cases]
    python = run_json([sys.executable, "conformance/run-python.py", str(FIXTURE)])
    typescript = run_json(
        ["pnpm", "exec", "tsx", "conformance/run-typescript.mts", str(FIXTURE)]
    )
    compare("Python", python, expected)
    compare("TypeScript", typescript, expected)
    compare("cross-port", python, typescript)
    verify_baseline()
    print(f"Conformance: {len(cases)} retained v3 cases passed in both ports")


if __name__ == "__main__":
    main()
