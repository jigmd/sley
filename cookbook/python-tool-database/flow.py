from nodes import create_task, initialize_database, list_tasks
from sley import Flow


def build_flow() -> Flow:
    initialize_database.link(create_task)
    create_task.link(list_tasks)
    return Flow(initialize_database)


database_flow = build_flow()
