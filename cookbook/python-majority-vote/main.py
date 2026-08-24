import argparse
import asyncio
from collections import Counter

import yaml
from sley import Context, Flow, ScopeResult, node
from utils import call_llm


@node
def dispatch(context: Context) -> None:
    for _ in range(context.state["num_tries"]):
        context.emit("attempt", context.state["question"])


@node
async def solve(context: Context) -> None:
    prompt = f"""
Answer this question:
{context.input}

Return strictly using the following YAML structure:
```yaml
thinking: your reasoning
answer: 0.123
```
"""
    response = await call_llm(prompt)
    if "```yaml" not in response:
        raise ValueError("response must contain a YAML block")
    parsed = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(parsed, dict) or "answer" not in parsed:
        raise ValueError("response is missing answer")
    context.end(str(parsed["answer"]))


def choose_majority(context: Context, result: ScopeResult) -> None:
    answers = list(result.outputs)
    best_answer, frequency = Counter(answers).most_common(1)[0]
    context.state["majority_answer"] = best_answer

    print("========================")
    print("All structured answers:", answers)
    print("Majority vote =>", best_answer)
    print("Frequency =>", frequency)
    print("========================")

    # Replace all worker terminals with one aggregate terminal.
    context.end(best_answer)


dispatch.link(solve, "attempt")
majority_flow = Flow(dispatch, concurrency=8, combine=choose_majority)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem")
    parser.add_argument("--tries", type=int, default=5)
    return parser.parse_args()


async def main() -> None:
    args = arguments()
    if args.tries < 1:
        raise ValueError("--tries must be positive")
    default_problem = """You work at a shoe factory with two size 4, two size 5,
and two size 6 shoes. An acceptable pair differs by at most one size. What is
the probability that three random pairs are all acceptable?"""

    state = await majority_flow.run(
        {"question": args.problem or default_problem, "num_tries": args.tries}
    )
    print("\n=== Final Answer ===")
    print(state["majority_answer"])
    print("====================")


if __name__ == "__main__":
    asyncio.run(main())
