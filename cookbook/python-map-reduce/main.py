import asyncio

from flow import resume_flow


async def main() -> None:
    print("Starting resume qualification processing...")
    state = await resume_flow.run({})

    print("\nDetailed evaluation results:")
    for filename, evaluation in state["evaluations"].items():
        marker = "✓" if evaluation.get("qualifies", False) else "✗"
        print(f"{marker} {evaluation.get('candidate_name', 'Unknown')} ({filename})")
    print("\nResume processing complete!")


if __name__ == "__main__":
    asyncio.run(main())
