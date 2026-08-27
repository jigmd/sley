import random

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


def dispatch_angles(context: Context) -> None:
    for angle in context.state["angles"]:
        context.emit("generate", angle)


async def generate_candidate(context: Context) -> None:
    angle = context.input
    response = await call_llm(
        f"""
Create a substantially different candidate for this request:
{context.state["request"]}

Candidate angle: {angle}

Honor the angle in structure and argument, not just wording. Return exactly:
```yaml
angle: {angle}
title: concise title
draft: complete candidate
```
"""
    )
    candidate = _yaml_block(response, "candidate")
    if (
        candidate.get("angle") != angle
        or not isinstance(candidate.get("title"), str)
        or not candidate["title"].strip()
        or not isinstance(candidate.get("draft"), str)
        or not candidate["draft"].strip()
    ):
        raise ValueError("candidate does not match its assigned angle")
    print(f"Generated {angle} candidate")
    context.end(candidate)


def collect_candidates(context: Context, result: ScopeResult) -> None:
    candidates = sorted(result.outputs, key=lambda candidate: candidate["angle"])
    context.emit(input=candidates)


async def _compare(left: dict, right: dict) -> tuple[dict, dict, dict]:
    response = await call_llm(
        f"""
Judge two anonymous candidates for the same request.

Candidate A:
Title: {left["title"]}
{left["draft"]}

Candidate B:
Title: {right["title"]}
{right["draft"]}

Return exactly:
```yaml
winner: A | B
evidence: the specific observable difference that decided the comparison
useful_element_from_loser: one useful element, or none
```

Choose on relevance, clarity, and usefulness. Do not infer authorship.
"""
    )
    verdict = _yaml_block(response, "judge verdict")
    if verdict.get("winner") not in {"A", "B"}:
        raise ValueError("judge winner must be A or B")
    if not isinstance(verdict.get("evidence"), str) or not isinstance(
        verdict.get("useful_element_from_loser"), str
    ):
        raise ValueError("judge verdict is missing evidence")
    winner = left if verdict["winner"] == "A" else right
    loser = right if verdict["winner"] == "A" else left
    return winner, loser, verdict


async def run_tournament(context: Context) -> None:
    pool = list(context.input)
    if len(pool) < 2:
        raise ValueError("the tournament needs at least two candidates")

    rng = random.Random(context.state["seed"])
    comparisons = []
    useful_elements = []
    round_number = 1

    while len(pool) > 1:
        rng.shuffle(pool)
        next_round = []
        while pool:
            if len(pool) == 1:
                next_round.append(pool.pop())
                continue

            pair = [pool.pop(), pool.pop()]
            rng.shuffle(pair)
            winner, loser, verdict = await _compare(pair[0], pair[1])
            comparisons.append(
                {
                    "round": round_number,
                    "evidence": verdict["evidence"],
                    "winner_title": winner["title"],
                }
            )
            useful = verdict["useful_element_from_loser"].strip()
            if useful.lower() != "none":
                useful_elements.append({"from": loser["title"], "element": useful})
            next_round.append(winner)
        pool = next_round
        round_number += 1

    context.state["comparisons"] = comparisons
    context.state["winner"] = pool[0]
    print(f"Blind tournament selected: {pool[0]['title']}")
    context.emit(input={"winner": pool[0], "useful_elements": useful_elements})


async def edit_winner(context: Context) -> None:
    response = await call_llm(
        f"""
Produce the final answer for this request:
{context.state["request"]}

Winning candidate:
{yaml.safe_dump(context.input["winner"], sort_keys=False)}

Potentially useful elements from other candidates:
{yaml.safe_dump(context.input["useful_elements"], sort_keys=False)}

Preserve the winner's strengths. Add an element only when it materially improves
the answer. Return only the final answer.
"""
    )
    if not response.strip():
        raise ValueError("editor returned an empty answer")
    context.state["final_answer"] = response.strip()
    print("Final editor completed the selected candidate")
