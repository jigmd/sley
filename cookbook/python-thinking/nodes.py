import textwrap

import yaml
from sley import Context
from utils import call_llm

STATUSES = {"pending", "done"}
ACTIONS = {"revise", "final"}


def parse_iteration(response: str) -> dict:
    if "```yaml" not in response:
        raise ValueError("response must contain a YAML block")
    parsed = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(parsed, dict):
        raise TypeError("iteration must be a YAML mapping")

    summary = parsed.get("progress_summary")
    plan = parsed.get("plan")
    action = parsed.get("next_action")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("progress_summary must be non-empty text")
    if not isinstance(plan, list) or not 1 <= len(plan) <= 10:
        raise ValueError("plan must contain between 1 and 10 steps")
    for step in plan:
        if not isinstance(step, dict):
            raise TypeError("each plan step must be a mapping")
        if not isinstance(step.get("step"), str) or not step["step"].strip():
            raise ValueError("each plan step needs non-empty text")
        if step.get("status") not in STATUSES:
            raise ValueError("plan status must be pending or done")
    if action not in ACTIONS:
        raise ValueError("next_action must be revise or final")

    answer = parsed.get("answer")
    if action == "final" and (not isinstance(answer, str) or not answer.strip()):
        raise ValueError("a final iteration must include a non-empty answer")
    return {
        "progress_summary": summary.strip(),
        "plan": plan,
        "next_action": action,
        "answer": answer.strip() if isinstance(answer, str) else None,
    }


def format_plan(plan: list[dict]) -> str:
    return "\n".join(f"- [{step['status']}] {step['step']}" for step in plan)


async def refine_plan(context: Context) -> None:
    state = context.state
    iteration_number = len(state["iterations"]) + 1
    previous = state["iterations"][-1] if state["iterations"] else None
    previous_summary = previous["progress_summary"] if previous else "No previous pass."
    previous_plan = format_plan(previous["plan"]) if previous else "No plan yet."

    prompt = textwrap.dedent(
        f"""
        You are performing iterative plan refinement for a problem. Do the
        reasoning privately. Return only a concise progress summary, an updated
        plan, and either a final answer or a request for another pass.

        Problem:
        {state["problem"]}

        Pass: {iteration_number} of {state["max_iterations"]}
        Previous progress summary: {previous_summary}
        Previous plan:
        {previous_plan}

        Return only this YAML shape inside a ```yaml block:
        ```yaml
        progress_summary: concise account of what changed or was verified
        plan:
          - step: define the approach
            status: done
          - step: verify the result
            status: pending
        next_action: revise  # revise or final
        answer: null         # required non-empty text when next_action is final
        ```

        Set next_action to final when the answer is ready. This is the last
        allowed pass when the pass number equals the maximum.
        """
    )
    iteration = parse_iteration(await call_llm(prompt))

    # Commit only after the provider response has passed the complete schema check.
    state["iterations"].append(iteration)
    print(f"\nPass {iteration_number}: {iteration['progress_summary']}")
    print(format_plan(iteration["plan"]))

    if iteration["next_action"] == "final":
        state["solution"] = iteration["answer"]
        print("\n=== Final Answer ===")
        print(state["solution"])
        return

    if iteration_number >= state["max_iterations"]:
        raise RuntimeError("the model reached the refinement limit without an answer")
    context.emit("continue")
