import asyncio
import sys

import yaml
from sley import Context, Flow, node
from utils import call_llm, call_tool, get_tools

SERVER = "simple_server.py"


@node
async def discover_tools(context: Context) -> None:
    print("🔍 Getting available tools...")
    tools = await get_tools(SERVER)
    context.state["tools"] = tools
    context.emit("decide")


@node
def decide_tool(context: Context) -> None:
    tool_info = "\n".join(
        f"- {tool.name}: {tool.description}; schema={tool.inputSchema}"
        for tool in context.state["tools"]
    )
    print("🤔 Analyzing question and deciding which tool to use...")
    response = call_llm(
        f"""
You can use these Model Context Protocol tools:
{tool_info}

Question: {context.state["question"]}

## NEXT ACTION
Return a YAML code block with this shape:
```yaml
tool: tool name
parameters:
  parameter: value
```
"""
    )
    if "```yaml" not in response:
        raise ValueError("decision must contain a YAML block")
    decision = yaml.safe_load(response.split("```yaml", 1)[1].split("```", 1)[0])
    if not isinstance(decision, dict) or not {"tool", "parameters"} <= decision.keys():
        raise ValueError("decision must contain tool and parameters")

    print(f"💡 Selected tool: {decision['tool']}")
    print(f"🔢 Extracted parameters: {decision['parameters']}")
    context.emit("execute", decision)


@node
async def execute_tool(context: Context) -> None:
    decision = context.input
    print(
        f"🔧 Executing tool '{decision['tool']}' "
        f"with parameters: {decision['parameters']}"
    )
    result = await call_tool(SERVER, decision["tool"], decision["parameters"])
    context.state["answer"] = result
    print(f"\n✅ Final Answer: {result}")


discover_tools.link(decide_tool, "decide")
decide_tool.link(execute_tool, "execute")
mcp_flow = Flow(discover_tools)


def question_from_args() -> str:
    return next(
        (arg[2:] for arg in sys.argv[1:] if arg.startswith("--")),
        "What is 982713504867129384651 plus 73916582047365810293746529?",
    )


async def main() -> None:
    question = question_from_args()
    print(f"🤔 Processing question: {question}")
    await mcp_flow.run({"question": question})


if __name__ == "__main__":
    asyncio.run(main())
