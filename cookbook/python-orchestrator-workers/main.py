import asyncio

from flow import brief_flow


async def main() -> None:
    state = await brief_flow.run(
        {
            "question": (
                "When should a small product team use synchronous or asynchronous "
                "collaboration?"
            ),
            "sources": {
                "meeting-cost": (
                    "Meetings interrupt focus for every attendee and should be "
                    "reserved for work that benefits from immediate exchange."
                ),
                "decision-speed": (
                    "Synchronous discussion can resolve ambiguous or contested "
                    "decisions quickly when the relevant people are present."
                ),
                "written-record": (
                    "Asynchronous written proposals preserve context and let "
                    "people contribute across schedules and time zones."
                ),
            },
        }
    )

    print("\nFinal comparison brief:")
    print(state["final_brief"])


if __name__ == "__main__":
    asyncio.run(main())
