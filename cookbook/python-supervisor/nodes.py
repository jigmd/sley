import yaml
from sley import Context
from utils import call_llm


def _yaml_block(response: str) -> dict:
    if "```yaml" not in response:
        raise ValueError("evaluation must contain a YAML block")
    parsed = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(parsed, dict):
        raise TypeError("evaluation must be a YAML object")
    return parsed


async def build_candidate(context: Context) -> None:
    state = context.state
    state["attempt"] += 1
    feedback = state.get("feedback") or "No previous feedback."
    state["candidate"] = await call_llm(
        f"""
Write a customer-facing incident update from the supplied facts.

Facts:
{state["facts"]}

Quality rubric:
{state["rubric"]}

Evaluator feedback from the previous attempt:
{feedback}

Do not invent facts. Return only the incident update.
"""
    )
    print(f"Builder produced attempt {state['attempt']}")
    context.emit("candidate")


async def evaluate_candidate(context: Context) -> None:
    state = context.state
    response = await call_llm(
        f"""
Act as an independent evaluator. You did not build the candidate.

Facts:
{state["facts"]}

Quality rubric:
{state["rubric"]}

Candidate:
{state["candidate"]}

Return exactly this YAML structure:
```yaml
verdict: approved | revise | unreachable
summary: one sentence
findings:
  - criterion: rubric criterion
    evidence: exact observable evidence from the candidate
    requested_change: the smallest change that would satisfy the criterion
```

Use `approved` only when every rubric criterion passes. Use `unreachable` only
when the supplied facts make the rubric impossible to satisfy. For an approved
candidate, return an empty `findings` list.
"""
    )
    evaluation = _yaml_block(response)
    verdict = evaluation.get("verdict")
    findings = evaluation.get("findings")
    if verdict not in {"approved", "revise", "unreachable"}:
        raise ValueError("verdict must be approved, revise, or unreachable")
    if not isinstance(evaluation.get("summary"), str) or not isinstance(findings, list):
        raise TypeError("evaluation is missing summary or findings")
    for finding in findings:
        if not isinstance(finding, dict) or any(
            not isinstance(finding.get(field), str) or not finding[field].strip()
            for field in ("criterion", "evidence", "requested_change")
        ):
            raise ValueError(
                "each finding needs criterion, evidence, and requested_change"
            )

    state["evaluation"] = evaluation
    if verdict == "approved":
        print("Evaluator approved candidate")
        context.emit("approved")
        return

    if verdict == "unreachable":
        state["stop_reason"] = "The evaluator found the rubric unreachable."
        print("Evaluator stopped: unreachable rubric")
        context.emit("stopped")
        return

    if state["attempt"] >= state["max_attempts"]:
        state["stop_reason"] = "The revision budget was exhausted."
        print("Evaluator stopped: revision budget exhausted")
        context.emit("stopped")
        return

    if not findings:
        raise ValueError("a revise verdict needs at least one finding")
    state["feedback"] = yaml.safe_dump(
        {"summary": evaluation["summary"], "findings": findings},
        sort_keys=False,
    )
    print("Evaluator requested a revision")
    context.emit("revise")
