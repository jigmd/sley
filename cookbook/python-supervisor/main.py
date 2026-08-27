import asyncio

from flow import supervisor_flow


async def main() -> None:
    state = await supervisor_flow.run(
        {
            "facts": """\
- Checkout was unavailable from 14:05 to 14:23 UTC.
- Deployments are paused while the team investigates.
- There is no evidence of lost orders.
- The next update will be posted at 15:00 UTC.""",
            "rubric": """\
1. State the affected service and exact time window.
2. Separate confirmed impact from what remains under investigation.
3. State the next action or update time.
4. Use no facts beyond those supplied.""",
            "attempt": 0,
            "max_attempts": 3,
        }
    )

    print("\nFinal candidate:")
    print(state["candidate"])
    if "stop_reason" in state:
        print(f"\nStopped: {state['stop_reason']}")


if __name__ == "__main__":
    asyncio.run(main())
