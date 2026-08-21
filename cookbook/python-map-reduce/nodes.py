from pathlib import Path

import yaml
from caskada import Context, ScopeResult
from utils import call_llm


def read_resumes(context: Context) -> None:
    resumes = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(Path("data").glob("*.txt"))
    }
    context.emit(input=resumes)


def map_resumes(context: Context) -> None:
    resumes = context.input
    if not resumes:
        context.end()
        return
    for filename, content in resumes.items():
        context.emit("evaluate", (filename, content))


async def evaluate_resume(context: Context) -> None:
    filename, content = context.input
    prompt = f"""
Evaluate the following resume for an advanced technical role.
Require a relevant bachelor's degree, three years of experience, and strong
technical skills.

{content}

Return a YAML code block:
```yaml
candidate_name: Jane Doe
qualifies: true
reasons:
  - reason
```
"""
    response = await call_llm(prompt)
    if "```yaml" not in response:
        raise ValueError("response must contain a YAML block")
    evaluation = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(evaluation, dict) or "qualifies" not in evaluation:
        raise ValueError("evaluation is missing required fields")
    context.end((filename, evaluation))


def collect_evaluations(context: Context, result: ScopeResult) -> None:
    # combine waits for every mapper branch, then replaces them with one input.
    context.emit(input=dict(result.outputs))


def reduce_results(context: Context) -> None:
    evaluations = context.input
    qualified = [
        value.get("candidate_name", "Unknown")
        for value in evaluations.values()
        if value.get("qualifies", False)
    ]
    total = len(evaluations)
    context.state["evaluations"] = evaluations
    context.state["summary"] = {
        "total_candidates": total,
        "qualified_count": len(qualified),
        "qualified_percentage": round(len(qualified) / total * 100, 1) if total else 0,
        "qualified_names": qualified,
    }

    summary = context.state["summary"]
    print("\n===== Resume Qualification Summary =====")
    print(f"Total candidates evaluated: {summary['total_candidates']}")
    print(
        f"Qualified candidates: {summary['qualified_count']} "
        f"({summary['qualified_percentage']}%)"
    )
    if qualified:
        print("\nQualified candidates:")
        for name in qualified:
            print(f"- {name}")
