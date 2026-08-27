import asyncio

from sley import Context, Flow, node
from utils import stream_llm


@node
def stream_answer(context: Context) -> None:
    try:
        for chunk in stream_llm(context.state["prompt"]):
            text = chunk.choices[0].delta.content
            if text:
                print(text, end="", flush=True)
    except KeyboardInterrupt:
        print("\nUser interrupted streaming.")
    else:
        print()


streaming_flow = Flow(stream_answer)


async def main() -> None:
    print("Press Ctrl+C to stop reading the stream.\n")
    await streaming_flow.run({"prompt": "What's the meaning of life?"})


if __name__ == "__main__":
    asyncio.run(main())
