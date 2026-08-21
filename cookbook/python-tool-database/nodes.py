from caskada import Context, node
from tools.database import execute_sql, init_db


@node
def initialize_database(context: Context) -> None:
    init_db()
    context.state["db_status"] = "Database initialized"


@node
def create_task(context: Context) -> None:
    execute_sql(
        "INSERT INTO tasks (title, description) VALUES (?, ?)",
        (context.state["task_title"], context.state["task_description"]),
    )
    context.state["task_status"] = "Task created successfully"


@node
def list_tasks(context: Context) -> None:
    context.state["tasks"] = execute_sql("SELECT * FROM tasks")
