import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI


def call_llm(prompt):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    response = client.chat.completions.create(
        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def server_parameters(path):
    return StdioServerParameters(command=sys.executable, args=[path])


async def get_tools(server_path):
    async with (
        stdio_client(server_parameters(server_path)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return (await session.list_tools()).tools


async def call_tool(server_path, name, arguments):
    async with (
        stdio_client(server_parameters(server_path)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments)
        return result.content[0].text
