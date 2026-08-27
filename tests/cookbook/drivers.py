"""Special black-box contracts for cookbooks without a finite CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Drivers live outside the staged cookbook, so explicitly give imports the same
# project-local resolution they get from `python main.py`.
sys.path.insert(0, str(Path.cwd()))


async def _a2a() -> None:
    from common.types import (
        Message,
        SendTaskRequest,
        TaskSendParams,
        TaskState,
        TextPart,
    )
    from task_manager import SleyTaskManager

    request = SendTaskRequest(
        id="cookbook-request",
        params=TaskSendParams(
            id="cookbook-task",
            message=Message(role="user", parts=[TextPart(text="What is Sley?")]),
            acceptedOutputModes=["text"],
        ),
    )
    response = await SleyTaskManager().on_send_task(request)
    assert response.error is None
    assert response.result is not None
    assert response.result.status.state == TaskState.COMPLETED
    assert response.result.artifacts
    assert response.result.artifacts[0].parts[0].text == "Cookbook smoke response"

    # Import the documented server entry point as well, so stale A2A server
    # dependencies and type declarations cannot escape the smoke test.
    import a2a_server  # noqa: F401

    print("A2A contract passed")


async def _agent() -> None:
    import nodes
    from flow import agent_flow

    responses = iter(
        (
            "```yaml\naction: search\nsearch_query: sley fixture\n```",
            "```yaml\naction: answer\nanswer: Research is sufficient.\n```",
            "Final answer from searched evidence",
        )
    )
    searches = []
    nodes.call_llm = lambda _prompt: next(responses)
    nodes.search_web = lambda query: searches.append(query) or ["fixture result"]

    state = await agent_flow.run({"question": "fixture"})
    assert searches == ["sley fixture"]
    assert state["answer"] == "Final answer from searched evidence"
    print("Agent search-route contract passed")


async def _crawler() -> None:
    from flow import create_flow
    from tools.crawler import normalize_public_url

    for unsafe in ("http://localhost", "http://127.0.0.1", "file:///etc/passwd"):
        try:
            normalize_public_url(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe crawl URL was accepted: {unsafe}")

    state = await create_flow().run(
        {"base_url": "https://example.test", "max_pages": 2}
    )
    assert "Total pages analyzed: 2" in state["report"]
    print("Crawler contract passed")


async def _fastapi_hitl() -> None:
    import server
    from flow import create_feedback_flow

    route_paths = {route.path for route in server.app.routes}
    assert {"/", "/submit", "/feedback/{task_id}", "/stream/{task_id}"} <= route_paths

    review = {"event": asyncio.Event(), "feedback": None, "waiting": False}
    queue = asyncio.Queue()
    run = asyncio.create_task(
        create_feedback_flow().run(
            {
                "task_input": "cookbook input",
                "review": review,
                "sse_queue": queue,
                "max_revisions": 3,
            }
        )
    )
    for feedback in (
        {"decision": "rejected", "instructions": "make it clearer"},
        {"decision": "approved", "instructions": None},
    ):
        while (await queue.get())["status"] != "waiting_for_review":
            pass
        review["feedback"] = feedback
        review["event"].set()

    state = await run
    assert state["final_result"] == "Revised: cookbook input (make it clearer)"
    print("FastAPI HITL contract passed")


async def _batch_node() -> None:
    from flow import create_flow

    with tempfile.TemporaryDirectory() as directory:
        empty_csv = Path(directory) / "empty.csv"
        empty_csv.write_text("amount\n", encoding="utf-8")
        result = await create_flow().start({"input_file": str(empty_csv)}).result()

    assert result.status == "failed"
    assert result.failure.kind == "handler"
    assert "statistics" not in result.state
    print("Batch node edge contract passed")


async def _majority_vote() -> None:
    import main as example

    assert example.vote_key("0.5") == example.vote_key("1/2")

    answers = iter(("0.5", "1/2", "different"))

    async def equivalent_answers(_prompt):
        return f"```yaml\nanswer: {next(answers)}\n```"

    example.call_llm = equivalent_answers
    state = await example.majority_flow.run({"question": "fixture", "num_tries": 3})
    assert example.vote_key(state["majority_answer"]) == example.vote_key("1/2")

    answers = iter(("red", "green", "blue"))
    example.call_llm = equivalent_answers
    state = await example.majority_flow.run({"question": "fixture", "num_tries": 3})
    assert state["majority_answer"] is None
    print("Majority vote edge contracts passed")


async def _mcp() -> None:
    from main import validate_decision

    tool = SimpleNamespace(
        name="add",
        inputSchema={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    )
    tools = [tool]
    valid = {"tool": "add", "parameters": {"a": 1, "b": 2}}
    assert validate_decision(valid, tools) == valid

    invalid = (
        {"tool": "missing", "parameters": {}},
        {"tool": "add", "parameters": {"a": 1}},
        {"tool": "add", "parameters": {"a": 1, "b": 2, "extra": 3}},
        {"tool": "add", "parameters": {"a": True, "b": 2}},
    )
    for decision in invalid:
        try:
            validate_decision(decision, tools)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"invalid MCP decision was accepted: {decision}")
    print("MCP validation contracts passed")


async def _nested_batch() -> None:
    from flow import create_school_flow

    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            Path("school").mkdir()
            empty_school = await create_school_flow().start({}).result()
            Path("school/class_1").mkdir()
            empty_class = await create_school_flow().start({}).result()
        finally:
            os.chdir(previous)

    for result in (empty_school, empty_class):
        assert result.status == "failed"
        assert result.failure.kind == "handler"
    print("Nested batch edge contracts passed")


async def _node_retry() -> None:
    import flow as example

    attempts = 0

    def succeeds_on_third(_prompt):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient fixture failure")
        return "Recovered summary"

    example.call_llm = succeeds_on_third
    state = await example.flow.run({"data": "fixture", "summary": None})
    assert attempts == 3
    assert state["summary"] == "Recovered summary"

    attempts = 0

    def always_fails(_prompt):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("persistent fixture failure")

    example.call_llm = always_fails
    state = await example.flow.run({"data": "fixture", "summary": None})
    assert attempts == 3
    assert state["summary"] == "There was an error processing your request."
    print("Retry and recovery contracts passed")


async def _rag() -> None:
    import nodes
    from flow import get_offline_flow, get_online_flow

    empty_state = await get_offline_flow().run(
        {"texts": [], "embeddings": None, "index": None}
    )
    assert empty_state["index"] is None

    nodes.get_embedding = lambda _text: [1.0, 2.0]
    mismatch = (
        await get_online_flow()
        .start(
            {
                "texts": ["fixture"],
                "index": [[1.0]],
                "query": "fixture",
                "query_embedding": None,
            }
        )
        .result()
    )
    assert mismatch.status == "failed"
    assert mismatch.failure.kind == "handler"
    print("RAG edge contracts passed")


async def _thinking() -> None:
    import nodes
    from flow import create_refinement_flow
    from sley import Flow, node

    revise = """```yaml
progress_summary: More verification is needed.
plan:
  - step: Verify the answer
    status: pending
next_action: revise
answer: null
```"""
    final = """```yaml
progress_summary: Verification is complete.
plan:
  - step: Verify the answer
    status: done
next_action: final
answer: Verified fixture answer
```"""
    responses = iter((revise, final))

    async def staged_response(_prompt):
        return next(responses)

    nodes.call_llm = staged_response
    state = await create_refinement_flow().run(
        {"problem": "fixture", "max_iterations": 4, "iterations": [], "solution": None}
    )
    assert len(state["iterations"]) == 2
    assert state["solution"] == "Verified fixture answer"

    async def malformed_response(_prompt):
        return "```yaml\nnext_action: final\n```"

    nodes.call_llm = malformed_response
    malformed = (
        await Flow(node(nodes.refine_plan))
        .start(
            {
                "problem": "fixture",
                "max_iterations": 1,
                "iterations": [],
                "solution": None,
            }
        )
        .result()
    )
    assert malformed.status == "failed"
    assert malformed.failure.kind == "handler"
    assert malformed.state["iterations"] == []

    async def endless_revision(_prompt):
        return revise

    nodes.call_llm = endless_revision
    limited = (
        await create_refinement_flow()
        .start(
            {
                "problem": "fixture",
                "max_iterations": 10,
                "iterations": [],
                "solution": None,
            }
        )
        .result()
    )
    assert limited.status == "failed"
    assert limited.failure.kind == "activation_limit"
    print("Thinking loop edge contracts passed")


async def _streamlit_hitl() -> None:
    expected = "Dummy rephrased text for the following input: cookbook input"
    from streamlit.testing.v1 import AppTest

    logging.getLogger("streamlit").setLevel(logging.ERROR)
    app = AppTest.from_file(str(Path.cwd() / "app.py")).run(timeout=10)
    assert not app.exception
    app.text_area[0].input("cookbook input").run(timeout=10)
    app.button[0].click().run(timeout=10)
    assert not app.exception
    assert app.session_state["stage"] == "awaiting_review"
    assert app.session_state["processed_output"] == expected

    approve = next(button for button in app.button if button.label == "Approve")
    approve.click().run(timeout=10)
    assert not app.exception
    assert app.session_state["stage"] == "completed"
    assert app.session_state["final_result"] == expected

    print("Streamlit HITL contract passed")


async def _text2sql() -> None:
    from main import run_text_to_sql
    from nodes import parse_sql

    for unsafe in ("DELETE FROM products", "SELECT 1; DELETE FROM products"):
        try:
            parse_sql(f"```yaml\nsql: {unsafe}\n```")
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe SQL was accepted: {unsafe}")

    state = await run_text_to_sql("total products per category")
    assert state["final_result"]
    print("Text-to-SQL contract passed")


async def _visualization() -> None:
    from async_flow import order_pipeline
    from visualize import flow_to_json, visualize_flow

    data = flow_to_json(order_pipeline)
    assert len(data["nodes"]) == 9
    assert len(data["flows"]) >= 3

    html_path = Path(
        visualize_flow(
            order_pipeline,
            "Cookbook Smoke",
            serve=False,
            output_dir="smoke-viz",
        )
    )
    json_path = html_path.with_suffix(".json")
    assert html_path.is_file()
    assert json_path.is_file()
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(written["nodes"]) == 9
    print("Visualization contract passed")


DRIVERS = {
    "a2a": _a2a,
    "agent": _agent,
    "batch_node": _batch_node,
    "crawler": _crawler,
    "fastapi_hitl": _fastapi_hitl,
    "majority_vote": _majority_vote,
    "mcp": _mcp,
    "nested_batch": _nested_batch,
    "node_retry": _node_retry,
    "rag": _rag,
    "streamlit_hitl": _streamlit_hitl,
    "text2sql": _text2sql,
    "thinking": _thinking,
    "visualization": _visualization,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("driver", choices=sorted(DRIVERS))
    args = parser.parse_args()
    asyncio.run(DRIVERS[args.driver]())


if __name__ == "__main__":
    main()
