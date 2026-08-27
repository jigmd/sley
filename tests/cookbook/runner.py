"""Discover, install, and execute cookbook projects as isolated black boxes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fake_api_server import fake_api_server

ROOT = Path(__file__).resolve().parents[2]
COOKBOOK = ROOT / "cookbook"
HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "catalog.json"
FAKES = HERE / "fakes"
SUBPROCESS_TIMEOUT_SECONDS = 10 * 60


class ContractError(RuntimeError):
    pass


def load_catalog() -> dict[str, dict[str, Any]]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("projects"), dict):
        raise ContractError("catalog.json must contain version 1 and a projects object")
    return data["projects"]


def discover_projects() -> set[str]:
    return {
        path.name
        for pattern in ("python-*", "typescript-*")
        for path in COOKBOOK.glob(pattern)
        if path.is_dir()
    }


def validate_catalog(catalog: dict[str, dict[str, Any]]) -> None:
    discovered = discover_projects()
    configured = set(catalog)
    missing = sorted(discovered - configured)
    stale = sorted(configured - discovered)
    if missing or stale:
        parts = []
        if missing:
            parts.append(f"missing contracts: {', '.join(missing)}")
        if stale:
            parts.append(f"stale contracts: {', '.join(stale)}")
        raise ContractError("; ".join(parts))

    for name, contract in catalog.items():
        runtime = contract.get("runtime")
        if runtime not in {"python", "typescript"}:
            raise ContractError(f"{name}: runtime must be python or typescript")
        if not contract.get("command") and not contract.get("driver"):
            raise ContractError(f"{name}: configure a command, driver, or both")
        if not contract.get("expect_stdout") and not contract.get("expect_files"):
            raise ContractError(
                f"{name}: contract needs at least one observable assertion"
            )
        if runtime == "python" and not (COOKBOOK / name / "requirements.txt").is_file():
            raise ContractError(f"{name}: requirements.txt is missing")
        if runtime == "typescript" and not (COOKBOOK / name / "package.json").is_file():
            raise ContractError(f"{name}: package.json is missing")


def _run_checked(command: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True, timeout=SUBPROCESS_TIMEOUT_SECONDS)


def install_project(name: str, contract: dict[str, Any], project_dir: Path) -> None:
    if contract["runtime"] == "python":
        # Install the checkout first so requirements resolve to the version
        # under test rather than the package registry.
        _run_checked(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--force-reinstall",
                str(ROOT / "python"),
            ],
            ROOT,
        )
        _run_checked(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                str(COOKBOOK / name / "requirements.txt"),
            ],
            ROOT,
        )
        return

    # Install the locked workspace and link the cookbook to this checkout
    # rather than the last published npm package.
    _run_checked(["pnpm", "install", "--frozen-lockfile"], ROOT)
    _run_checked(["pnpm", "--dir", "typescript", "build"], ROOT)
    _link_typescript_workspace(name, project_dir)


def _link_typescript_workspace(name: str, project_dir: Path) -> None:
    source_modules = COOKBOOK / name / "node_modules"
    if not source_modules.is_dir():
        raise ContractError(
            f"{name}: workspace dependencies are missing; rerun with --install"
        )
    staged_workspace = project_dir.parents[1]
    os.symlink(
        ROOT / "node_modules",
        staged_workspace / "node_modules",
        target_is_directory=True,
    )
    os.symlink(
        ROOT / "typescript", staged_workspace / "typescript", target_is_directory=True
    )
    staged_modules = project_dir / "node_modules"
    shutil.copytree(source_modules, staged_modules, symlinks=True)
    staged_scope = staged_modules / "@jigging"
    staged_scope.mkdir(exist_ok=True)
    staged_sley = staged_scope / "sley"
    if staged_sley.is_symlink():
        staged_sley.unlink()
    elif staged_sley.exists():
        raise ContractError(
            f"{name}: expected @jigging/sley dependency to be a symlink"
        )
    os.symlink(staged_workspace / "typescript", staged_sley, target_is_directory=True)


def _stage_project(name: str, temp_root: Path) -> Path:
    workspace = temp_root / "workspace"
    staged = workspace / "cookbook" / name
    staged.parent.mkdir(parents=True)
    shutil.copytree(
        COOKBOOK / name,
        staged,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
    )
    shutil.copy2(ROOT / "README.md", workspace / "README.md")
    return staged


def _clean_outputs(project_dir: Path, paths: list[str]) -> None:
    for relative in paths:
        target = (project_dir / relative).resolve()
        if project_dir.resolve() not in target.parents:
            raise ContractError(
                f"refusing to clean a path outside the staged project: {relative}"
            )
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _commands(contract: dict[str, Any]) -> list[list[str]]:
    commands = []
    if contract.get("command"):
        command = list(contract["command"])
        if contract["runtime"] == "python" and command[0] == "python":
            command[0] = sys.executable
        commands.append(command)
    if contract.get("driver"):
        commands.append([sys.executable, str(HERE / "drivers.py"), contract["driver"]])
    return commands


def _typecheck_typescript(project_dir: Path) -> None:
    sources = sorted(path.name for path in project_dir.glob("*.ts"))
    if not sources:
        raise ContractError("TypeScript cookbook has no source files")
    _run_checked(
        [
            str(project_dir / "node_modules" / ".bin" / "tsc"),
            "--noEmit",
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--moduleResolution",
            "bundler",
            "--skipLibCheck",
            "false",
            *sources,
        ],
        project_dir,
    )


def _environment(api_url: str) -> dict[str, str]:
    env = os.environ.copy()
    # Keep ambient provider credentials from bypassing the local protocol fake.
    env.pop("OPENROUTER_API_KEY", None)
    python_path = os.pathsep.join([str(ROOT / "python"), str(FAKES)])
    if env.get("PYTHONPATH"):
        python_path += os.pathsep + env["PYTHONPATH"]
    env.update(
        {
            "PYTHONPATH": python_path,
            "PYTHONUNBUFFERED": "1",
            "SLEY_COOKBOOK_TEST": "1",
            "OPENAI_API_KEY": "cookbook-test-key",
            "OPENAI_BASE_URL": f"{api_url}/v1",
            "ANTHROPIC_API_KEY": "cookbook-test-key",
            "ANTHROPIC_BASE_URL": api_url,
            "SERPAPI_API_KEY": "cookbook-test-key",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    return env


def _assert_contract(
    name: str, contract: dict[str, Any], project_dir: Path, output: str
) -> None:
    missing_output = [
        text for text in contract.get("expect_stdout", []) if text not in output
    ]
    if missing_output:
        raise ContractError(
            f"{name}: stdout did not contain {missing_output!r}\n\n{output}"
        )

    for expectation in contract.get("expect_files", []):
        matches = list(project_dir.glob(expectation["glob"]))
        expected_count = expectation["count"]
        if len(matches) != expected_count:
            raise ContractError(
                f"{name}: {expectation['glob']!r} matched {len(matches)} files, expected {expected_count}"
            )
        empty = [
            path for path in matches if path.is_file() and path.stat().st_size == 0
        ]
        if empty:
            raise ContractError(f"{name}: generated empty files: {empty}")
        required_text = expectation.get("contains")
        if required_text:
            missing_text = [
                path
                for path in matches
                if required_text not in path.read_text(encoding="utf-8")
            ]
            if missing_text:
                raise ContractError(
                    f"{name}: generated files missing {required_text!r}: {missing_text}"
                )


def run_project(name: str, *, install: bool = False, keep: bool = False) -> None:
    catalog = load_catalog()
    validate_catalog(catalog)
    if name not in catalog:
        raise ContractError(f"unknown cookbook project: {name}")
    contract = catalog[name]

    temp_context = tempfile.TemporaryDirectory(prefix=f"sley-{name}-")
    temp_root = Path(temp_context.name)
    project_dir = _stage_project(name, temp_root)
    try:
        _clean_outputs(project_dir, contract.get("clean", []))
        if install:
            install_project(name, contract, project_dir)
        elif contract["runtime"] == "typescript":
            _link_typescript_workspace(name, project_dir)

        if contract["runtime"] == "typescript":
            _typecheck_typescript(project_dir)

        timeout = int(contract.get("timeout", 30))
        outputs = []
        with fake_api_server() as api_url:
            for command in _commands(contract):
                print(f"[{name}] {' '.join(command)}", flush=True)
                try:
                    result = subprocess.run(
                        command,
                        cwd=project_dir,
                        env=_environment(api_url),
                        input=contract.get("stdin"),
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    captured = exc.stdout or ""
                    raise ContractError(
                        f"{name}: timed out after {timeout}s\n\n{captured}"
                    ) from exc

                print(result.stdout, end="")
                outputs.append(result.stdout)
                if result.returncode != 0:
                    raise ContractError(
                        f"{name}: exited with status {result.returncode}\n\n{result.stdout}"
                    )

        _assert_contract(name, contract, project_dir, "".join(outputs))
        print(f"[{name}] contract passed", flush=True)
    finally:
        if keep:
            kept = ROOT / ".cookbook-test-artifacts" / name
            if kept.exists():
                shutil.rmtree(kept)
            kept.parent.mkdir(exist_ok=True)
            shutil.copytree(project_dir, kept)
            print(f"Kept staged project at {kept}")
        temp_context.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("validate", help="validate catalog coverage and structure")
    list_parser = subparsers.add_parser(
        "list", help="list projects for CI matrix generation"
    )
    list_parser.add_argument("--json", action="store_true")
    run_parser = subparsers.add_parser("run", help="run one cookbook contract")
    run_parser.add_argument("project")
    run_parser.add_argument(
        "--install", action="store_true", help="install documented dependencies first"
    )
    run_parser.add_argument(
        "--keep", action="store_true", help="keep the staged project for debugging"
    )
    args = parser.parse_args()

    catalog = load_catalog()
    validate_catalog(catalog)
    if args.action == "validate":
        print(f"Catalog covers all {len(catalog)} cookbook projects")
    elif args.action == "list":
        names = sorted(catalog)
        print(json.dumps(names) if args.json else "\n".join(names))
    else:
        run_project(args.project, install=args.install, keep=args.keep)


if __name__ == "__main__":
    try:
        main()
    except ContractError as exc:
        print(f"cookbook contract failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
