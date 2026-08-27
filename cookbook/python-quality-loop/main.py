import asyncio

from flow import quality_flow


async def main() -> None:
    state = await quality_flow.run({"seed": 11})

    print(f"\nOutcome: {state.get('outcome', 'stopped')}")
    for component in state["component_results"]:
        print(
            f"- {component['task']['id']}: {component['status']} "
            f"after {component['attempt']} attempt(s)"
        )
    print("\nFinal artifact:")
    print(state.get("artifact", "No integrated artifact was produced."))
    if "stop_reason" in state:
        print(f"\nResidual gap: {state['stop_reason']}")


if __name__ == "__main__":
    asyncio.run(main())
