import asyncio

from flow import database_flow


async def main() -> None:
    state = await database_flow.run(
        {
            "task_title": "Example Task",
            "task_description": "This is an example task created using Sley",
        }
    )

    print("Database Status:", state["db_status"])
    print("Task Status:", state["task_status"])
    print("\nAll Tasks:")
    for task in state["tasks"]:
        print(f"- ID: {task[0]}")
        print(f"  Title: {task[1]}")
        print(f"  Description: {task[2]}")
        print(f"  Status: {task[3]}")
        print(f"  Created: {task[4]}\n")


if __name__ == "__main__":
    asyncio.run(main())
