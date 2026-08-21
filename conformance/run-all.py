from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BASELINE_PATH = ROOT / "internal" / "v3-implementation-baseline.json"


def _verify_baseline() -> None:
    manifest = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    for group in ("authority", "verification_tools"):
        for record in manifest[group]:
            path = ROOT / record["path"]
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != record["sha256"]:
                raise AssertionError(f"baseline hash mismatch: {record['path']}")


def _run(command: list[str]) -> bytes:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    return completed.stdout


def main() -> None:
    _verify_baseline()
    python_snapshot = _run([sys.executable, "conformance/run-python.py"])
    typescript_snapshot = _run(
        ["node", "--import=tsx", "conformance/run-typescript.mts"]
    )
    if python_snapshot != typescript_snapshot:
        raise AssertionError(
            "Python and TypeScript reference snapshots differ\n"
            f"python={python_snapshot.decode()}\n"
            f"typescript={typescript_snapshot.decode()}"
        )
    fixture_count = len(json.loads(python_snapshot)["fixtures"])
    print(
        f"Phase 0: {fixture_count} exact fixtures agree across Python and TypeScript",
        flush=True,
    )
    definitions = _run([sys.executable, "conformance/run-definitions.py"])
    sys.stdout.buffer.write(definitions)
    compilation = _run([sys.executable, "conformance/run-compile.py"])
    sys.stdout.buffer.write(compilation)
    compile_scale = _run([sys.executable, "conformance/run-compile-scale.py"])
    sys.stdout.buffer.write(compile_scale)
    runtime_scale = _run([sys.executable, "conformance/run-runtime-scale.py"])
    sys.stdout.buffer.write(runtime_scale)
    serial_execution = _run([sys.executable, "conformance/run-serial-production.py"])
    sys.stdout.buffer.write(serial_execution)
    failure_recovery = _run([sys.executable, "conformance/run-failure-recovery.py"])
    sys.stdout.buffer.write(failure_recovery)
    scheduling_cancellation = _run(
        [sys.executable, "conformance/run-scheduling-cancellation.py"]
    )
    sys.stdout.buffer.write(scheduling_cancellation)
    events_reports_limits = _run(
        [sys.executable, "conformance/run-events-reports-limits.py"]
    )
    sys.stdout.buffer.write(events_reports_limits)


if __name__ == "__main__":
    main()
