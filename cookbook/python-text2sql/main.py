import asyncio
import sys
from pathlib import Path

from flow import text_to_sql_flow
from populate_db import DB_FILE, populate_database


async def run_text_to_sql(query, db_path=DB_FILE, max_debug_attempts=3):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if max_debug_attempts < 1:
        raise ValueError("max_debug_attempts must be positive")
    if not Path(db_path).is_file():
        populate_database(db_path)

    print("\n=== Starting Text-to-SQL Workflow ===")
    print(f"Query: {query}")
    state = await text_to_sql_flow.run(
        {
            "db_path": db_path,
            "natural_query": query.strip(),
            "max_debug_attempts": max_debug_attempts,
        }
    )

    if "final_error" in state:
        print("\n=== Workflow Completed with Error ===")
        print(state["final_error"])
    else:
        print("\n=== Workflow Completed Successfully ===")
    return state


if __name__ == "__main__":
    natural_query = (
        " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "total products per category"
    )
    asyncio.run(run_text_to_sql(natural_query))
