import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cookbook_runner", HERE / "runner.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(HERE))
SPEC.loader.exec_module(runner)


def test_every_cookbook_has_a_valid_contract():
    catalog = runner.load_catalog()
    runner.validate_catalog(catalog)
    assert set(catalog) == runner.discover_projects()


def test_python_sources_compile():
    for project in sorted(runner.discover_projects()):
        if not project.startswith("python-"):
            continue
        for source in (runner.COOKBOOK / project).rglob("*.py"):
            compile(source.read_text(encoding="utf-8"), str(source), "exec")


def test_catalog_is_stably_sorted():
    raw = json.loads(runner.CATALOG_PATH.read_text(encoding="utf-8"))
    names = list(raw["projects"])
    assert names == sorted(names)


def test_typescript_cookbooks_link_the_workspace_package():
    lockfile = (runner.ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    for project in sorted(runner.discover_projects()):
        if not project.startswith("typescript-"):
            continue
        importer = re.search(
            rf"^  cookbook/{re.escape(project)}:\n(?P<body>.*?)(?=^  \S|\Z)",
            lockfile,
            re.MULTILINE | re.DOTALL,
        )
        assert importer is not None, f"{project}: missing pnpm lockfile importer"
        assert "version: link:../../typescript" in importer.group("body"), (
            f"{project}: @jigging/sley must link to the workspace package"
        )


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> bool:
        if name in visiting:
            return True
        if name in visited:
            return False
        visiting.add(name)
        if any(visit(target) for target in edges.get(name, ())):
            return True
        visiting.remove(name)
        visited.add(name)
        return False

    return any(visit(name) for name in edges)


def test_python_cycles_have_activation_backstops():
    for source in runner.COOKBOOK.glob("python-*/*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        edges: dict[str, set[str]] = {}
        flow_calls = []
        for item in ast.walk(tree):
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute)
                and item.func.attr == "link"
                and isinstance(item.func.value, ast.Name)
                and item.args
                and isinstance(item.args[0], ast.Name)
            ):
                edges.setdefault(item.func.value.id, set()).add(item.args[0].id)
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "Flow"
            ):
                flow_calls.append(item)

        if _has_cycle(edges):
            assert any(
                any(keyword.arg == "max_activations" for keyword in call.keywords)
                for call in flow_calls
            ), f"{source}: cyclic topology needs max_activations"


def test_typescript_cycles_have_activation_backstops():
    link = re.compile(r"\b([A-Za-z_$][\w$]*)\.link\(\s*([A-Za-z_$][\w$]*)")
    for project in runner.COOKBOOK.glob("typescript-*"):
        for source in project.rglob("*.ts"):
            text = source.read_text(encoding="utf-8")
            edges: dict[str, set[str]] = {}
            for start, target in link.findall(text):
                edges.setdefault(start, set()).add(target)
            if _has_cycle(edges):
                assert "maxActivations" in text, (
                    f"{source}: cyclic topology needs maxActivations"
                )


def test_provider_examples_do_not_embed_credentials_or_retired_models():
    forbidden = {
        "YOUR_API_KEY_HERE",
        '"your-api-key"',
        "'your-api-key'",
        "claude-3-7-sonnet-20250219",
        "text-embedding-ada-002",
    }
    for project in runner.discover_projects():
        for source in (runner.COOKBOOK / project).rglob("*"):
            if source.suffix not in {".py", ".ts", ".js"}:
                continue
            text = source.read_text(encoding="utf-8")
            found = sorted(token for token in forbidden if token in text)
            assert not found, f"{source}: forbidden provider configuration {found}"


def _project_source(project: str) -> str:
    files = (runner.COOKBOOK / project).rglob("*")
    return "\n".join(
        source.read_text(encoding="utf-8")
        for source in files
        if source.suffix in {".py", ".ts"}
    )


def test_provider_configuration_is_explicit_and_overridable():
    for project in runner.discover_projects():
        text = _project_source(project)
        if re.search(r"(?:from openai import|import OpenAI)", text):
            explicit_key = 'os.environ["OPENAI_API_KEY"]' in text
            explicit_key |= (
                "process.env.OPENAI_API_KEY" in text and "if (!apiKey)" in text
            )
            assert explicit_key, f"{project}: OpenAI key must fail clearly when absent"
            assert re.search(r"OPENAI_[A-Z_]*MODEL", text), (
                f"{project}: OpenAI model must be overridable"
            )

        if re.search(r"from anthropic import", text):
            assert 'os.environ["ANTHROPIC_API_KEY"]' in text, (
                f"{project}: Anthropic key must fail clearly when absent"
            )
            assert "ANTHROPIC_MODEL" in text, (
                f"{project}: Anthropic model must be overridable"
            )


def test_catalog_mechanisms_are_visible_in_source():
    catalog_path = runner.ROOT / "docs" / "examples" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    markers = {
        "combine": ("combine=", "combine(context"),
        "concurrency": ("concurrency=", "concurrency:"),
        "retry": ("RetryPolicy", "retry:"),
        "recover": ("recover=", "recover:"),
        "max_activations": ("max_activations=",),
        "maxActivations": ("maxActivations:",),
        "compile": (".compile(",),
        "describe": (".describe(",),
        "exits": ("exits=",),
    }

    for groups in catalog.values():
        for group in groups:
            for entry in group["projects"]:
                text = _project_source(entry["project"])
                for mechanism in entry["mechanisms"]:
                    if mechanism == "nested Flow":
                        assert text.count("Flow(") >= 2, (
                            f"{entry['project']}: nested Flow is not visible in source"
                        )
                    elif mechanism in markers:
                        assert any(marker in text for marker in markers[mechanism]), (
                            f"{entry['project']}: {mechanism} is not visible in source"
                        )
