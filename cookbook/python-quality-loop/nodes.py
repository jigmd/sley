import random
from pathlib import Path

import yaml
from sley import Context, ScopeResult
from utils import call_llm


def _yaml_block(response: str, label: str) -> dict:
    if "```yaml" not in response:
        raise ValueError(f"{label} must contain a YAML block")
    parsed = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a YAML object")
    return parsed


def load_benchmark(context: Context) -> None:
    benchmark = yaml.safe_load(Path("benchmark.yml").read_text(encoding="utf-8"))
    if not isinstance(benchmark, dict):
        raise ValueError("benchmark.yml must contain an object")

    acceptance = benchmark.get("acceptance")
    components = benchmark.get("components")
    if (
        not isinstance(benchmark.get("foundation"), dict)
        or not isinstance(benchmark.get("dimensions"), list)
        or not isinstance(acceptance, dict)
        or not isinstance(components, list)
        or not components
    ):
        raise ValueError("benchmark is missing its quality contract")

    for key in (
        "comparisons",
        "required_wins",
        "max_component_attempts",
        "max_integration_attempts",
    ):
        if not isinstance(acceptance.get(key), int) or acceptance[key] < 1:
            raise ValueError(f"acceptance.{key} must be positive")

    context.state["benchmark"] = benchmark
    print(f"Quality bar: {benchmark['title']}")
    print(f"Comparison slice: {benchmark['slice']}")


def dispatch_components(context: Context) -> None:
    benchmark = context.state["benchmark"]
    for task in benchmark["components"]:
        context.emit(
            "improve",
            {
                "task": task,
                "attempt": 0,
                "feedback": "No previous feedback.",
            },
        )


async def build_component(context: Context) -> None:
    job = context.input
    task = job["task"]
    response = await call_llm(
        f"""
Reference-grounded quality loop component builder.

Frozen foundation:
{yaml.safe_dump(context.state["benchmark"]["foundation"], sort_keys=False)}

Ranked dimensions:
{yaml.safe_dump(context.state["benchmark"]["dimensions"], sort_keys=False)}

Component goal:
{task["goal"]}

Reference slice:
{task["reference"]}

Evaluator feedback:
{job["feedback"]}

Write one candidate section. Match the reference's useful qualities without
copying its wording. Return only the section.
"""
    )
    if not response.strip():
        raise ValueError("component builder returned an empty section")
    updated = {
        **job,
        "attempt": job["attempt"] + 1,
        "draft": response.strip(),
    }
    print(f"Built {task['id']} attempt {updated['attempt']}")
    context.emit("evaluate", updated)


async def evaluate_component(context: Context) -> None:
    job = context.input
    task = job["task"]
    missing = [
        phrase
        for phrase in task["required_phrases"]
        if phrase.lower() not in job["draft"].lower()
    ]

    artifacts = [task["reference"].strip(), job["draft"]]
    rng = random.Random(f"{task['id']}:{job['attempt']}")
    rng.shuffle(artifacts)
    candidate_label = "A" if artifacts[0] == job["draft"] else "B"

    response = await call_llm(
        f"""
Reference-grounded quality loop component judge. Compare equivalent text slices.

Artifact A:
{artifacts[0]}

Artifact B:
{artifacts[1]}

Top-ranked dimensions:
{yaml.safe_dump(context.state["benchmark"]["dimensions"], sort_keys=False)}

Return exactly:
```yaml
winner: A | B | tie
evidence: the observable difference that decided the verdict
flip_condition: the smallest specific change that would flip the verdict
reachable: true
```
"""
    )
    verdict = _yaml_block(response, "component verdict")
    if verdict.get("winner") not in {"A", "B", "tie"}:
        raise ValueError("component winner must be A, B, or tie")
    if (
        not isinstance(verdict.get("reachable"), bool)
        or not isinstance(verdict.get("evidence"), str)
        or not isinstance(verdict.get("flip_condition"), str)
    ):
        raise ValueError("component verdict is missing required fields")

    parity = verdict["winner"] in {candidate_label, "tie"}
    updated = {**job, "missing": missing, "verdict": verdict}
    if not verdict["reachable"]:
        updated["status"] = "unreachable"
        context.emit("unreachable", updated)
        return
    if not missing and parity:
        updated["status"] = "passed"
        print(f"Component reached parity: {task['id']}")
        context.emit("passed", updated)
        return

    limit = context.state["benchmark"]["acceptance"]["max_component_attempts"]
    if job["attempt"] >= limit:
        updated["status"] = "capped"
        context.emit("capped", updated)
        return

    updated["feedback"] = yaml.safe_dump(
        {
            "missing_required_phrases": missing,
            "evidence": verdict["evidence"],
            "flip_condition": verdict["flip_condition"],
        },
        sort_keys=False,
    )
    context.emit("revise", updated)


def collect_components(context: Context, result: ScopeResult) -> None:
    components = sorted(result.outputs, key=lambda item: item["task"]["id"])
    context.state["component_results"] = components
    failed = [item for item in components if item["status"] != "passed"]
    if failed:
        status = failed[0]["status"]
        context.state["stop_reason"] = (
            "A component benchmark was unreachable."
            if status == "unreachable"
            else "A component exhausted its iteration cap."
        )
        context.emit("stopped", components)
        return

    print("Every component reached its local quality bar")
    context.emit("ready", components)


def settle_component(context: Context) -> None:
    context.end(context.input)


async def integrate_components(context: Context) -> None:
    state = context.state
    state["integration_attempt"] += 1
    feedback = state.get("integration_feedback") or "No previous feedback."
    sections = [
        {
            "id": item["task"]["id"],
            "draft": item["draft"],
        }
        for item in context.input
    ]
    response = await call_llm(
        f"""
Reference-grounded quality loop integration editor.

Frozen foundation:
{yaml.safe_dump(state["benchmark"]["foundation"], sort_keys=False)}

Component sections:
{yaml.safe_dump(sections, sort_keys=False)}

Whole-artifact feedback:
{feedback}

Assemble one coherent migration note. Resolve seams and duplicated ideas while
preserving every required phrase. Return only the note.
"""
    )
    if not response.strip():
        raise ValueError("integration editor returned an empty artifact")
    state["artifact"] = response.strip()
    print(f"Integrated whole artifact attempt {state['integration_attempt']}")
    context.emit(input=context.input)


async def judge_whole(context: Context) -> None:
    state = context.state
    benchmark = state["benchmark"]
    acceptance = benchmark["acceptance"]
    required_phrases = [
        phrase
        for component in benchmark["components"]
        for phrase in component["required_phrases"]
    ]
    missing = [
        phrase
        for phrase in required_phrases
        if phrase.lower() not in state["artifact"].lower()
    ]
    reference = "\n\n".join(
        component["reference"].strip() for component in benchmark["components"]
    )

    wins = 0
    reachable = True
    evidence = []
    flip_conditions = []
    for comparison in range(acceptance["comparisons"]):
        artifacts = [reference, state["artifact"]]
        rng = random.Random(
            f"{state['integration_attempt']}:{comparison}:{state['seed']}"
        )
        rng.shuffle(artifacts)
        candidate_label = "A" if artifacts[0] == state["artifact"] else "B"
        response = await call_llm(
            f"""
Reference-grounded quality loop whole-artifact judge.

Artifact A:
{artifacts[0]}

Artifact B:
{artifacts[1]}

Ranked dimensions:
{yaml.safe_dump(benchmark["dimensions"], sort_keys=False)}

Return exactly:
```yaml
winner: A | B | tie
evidence: the observable difference that decided the verdict
flip_condition: the smallest specific change that would flip the verdict
reachable: true
```
"""
        )
        verdict = _yaml_block(response, "whole-artifact verdict")
        if verdict.get("winner") not in {"A", "B", "tie"}:
            raise ValueError("whole-artifact winner must be A, B, or tie")
        if (
            not isinstance(verdict.get("reachable"), bool)
            or not isinstance(verdict.get("evidence"), str)
            or not isinstance(verdict.get("flip_condition"), str)
        ):
            raise ValueError("whole-artifact verdict is missing required fields")
        if verdict["winner"] in {candidate_label, "tie"}:
            wins += 1
        reachable = reachable and verdict["reachable"]
        evidence.append(verdict["evidence"])
        flip_conditions.append(verdict["flip_condition"])

    print(f"Blind whole-artifact verdicts: {wins}/{acceptance['comparisons']}")
    if not missing and wins >= acceptance["required_wins"]:
        state["outcome"] = "parity"
        context.emit("approved")
        return

    material_gap = yaml.safe_dump(
        {"missing": missing, "flip_conditions": sorted(set(flip_conditions))},
        sort_keys=True,
    )
    history = state.setdefault("gap_history", [])
    history.append(material_gap)

    if not reachable:
        state["stop_reason"] = "The judge found the benchmark unreachable."
    elif state["integration_attempt"] >= acceptance["max_integration_attempts"]:
        state["stop_reason"] = "The integration iteration cap was reached."
    elif len(history) >= 2 and history[-1] == history[-2]:
        state["stop_reason"] = "Two passes found the same material gap."
    else:
        state["integration_feedback"] = yaml.safe_dump(
            {
                "missing_required_phrases": missing,
                "evidence": evidence,
                "flip_conditions": flip_conditions,
            },
            sort_keys=False,
        )
        context.emit("revise", context.input)
        return

    state["outcome"] = "stopped"
    print(f"Quality loop stopped: {state['stop_reason']}")
    context.emit("stopped")


def initialize_run(context: Context) -> None:
    context.state["integration_attempt"] = 0
    context.state["gap_history"] = []
