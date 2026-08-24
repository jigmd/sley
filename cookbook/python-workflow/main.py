import asyncio
import sys

from flow import article_flow


async def main(topic: str = "AI Safety") -> None:
    print(f"\n=== Starting Article Workflow on Topic: {topic} ===\n")

    # run() returns the final state owned by this workflow invocation.
    state = await article_flow.run({"topic": topic})

    print("\n=== Workflow Completed ===\n")
    print(f"Topic: {state['topic']}")
    print(f"Outline Length: {len(state['outline'])} characters")
    print(f"Draft Length: {len(state['draft'])} characters")
    print(f"Final Article Length: {len(state['final_article'])} characters")


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "AI Safety"))
