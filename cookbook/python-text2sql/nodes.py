import re
import sqlite3
from pathlib import Path

import yaml
from sley import Context, node
from utils import call_llm

MAX_RESULT_ROWS = 100


def validate_read_query(sql: str) -> str:
    query = sql.strip().rstrip(";").strip()
    if not query:
        raise ValueError("SQL query cannot be empty")
    if ";" in query:
        raise ValueError("SQL response must contain exactly one statement")
    if not re.match(r"(?is)^(select|with)\b", query):
        raise ValueError("SQL response must be a read-only SELECT query")
    return query


def connect_read_only(db_path: str) -> sqlite3.Connection:
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def parse_sql(response):
    if "```yaml" not in response:
        raise ValueError("response must contain a YAML block")
    result = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(result, dict) or not isinstance(result.get("sql"), str):
        raise TypeError("response must contain a SQL string")
    return validate_read_query(result["sql"])


@node
def get_schema(context: Context) -> None:
    with connect_read_only(context.state["db_path"]) as connection:
        cursor = connection.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        lines = []
        for (table,) in tables:
            lines.append(f"Table: {table}")
            quoted_table = table.replace('"', '""')
            for column in cursor.execute(
                f'PRAGMA table_info("{quoted_table}")'
            ).fetchall():
                lines.append(f"  - {column[1]} ({column[2]})")

    context.state["schema"] = "\n".join(lines)
    print("\n===== DB SCHEMA =====\n")
    print(context.state["schema"])


@node
def generate_sql(context: Context) -> None:
    response = call_llm(
        f"""
Given this SQLite schema:
{context.state["schema"]}

Question: {context.state["natural_query"]}

Respond only with a YAML code block containing the SQL query:
```yaml
sql: |
  SELECT ...
```
"""
    )
    context.state["generated_sql"] = parse_sql(response)
    context.state["debug_attempts"] = 0
    print("\n===== GENERATED SQL (Attempt 1) =====\n")
    print(context.state["generated_sql"])


@node
def execute_sql(context: Context) -> None:
    sql = context.state["generated_sql"]
    try:
        with connect_read_only(context.state["db_path"]) as connection:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
            if len(rows) > MAX_RESULT_ROWS:
                raise ValueError(
                    f"query returned more than {MAX_RESULT_ROWS} rows; add a LIMIT"
                )
            columns = [column[0] for column in cursor.description or []]
    except (sqlite3.Error, ValueError) as error:
        context.state["execution_error"] = str(error)
        context.state["debug_attempts"] += 1
        attempts = context.state["debug_attempts"]
        print(f"\n===== SQL EXECUTION FAILED (Attempt {attempts}) =====\n")
        print(error)

        if attempts >= context.state["max_debug_attempts"]:
            context.state["final_error"] = str(error)
            return
        context.emit("debug")
        return

    context.state["final_result"] = rows
    context.state["result_columns"] = columns
    print("\n===== SQL EXECUTION SUCCESS =====\n")
    if columns:
        print(" | ".join(columns))
    for row in rows:
        print(" | ".join(map(str, row)))


@node
def debug_sql(context: Context) -> None:
    response = call_llm(
        f"""
The SQLite query below failed:
```sql
{context.state["generated_sql"]}
```

Question: {context.state["natural_query"]}
Schema: {context.state["schema"]}
Error: {context.state["execution_error"]}

Respond only with a YAML code block containing the corrected SQL query:
```yaml
sql: |
  SELECT ...
```
"""
    )
    context.state["generated_sql"] = parse_sql(response)
    context.state.pop("execution_error", None)
    attempt = context.state["debug_attempts"] + 1
    print(f"\n===== REVISED SQL (Attempt {attempt}) =====\n")
    print(context.state["generated_sql"])
