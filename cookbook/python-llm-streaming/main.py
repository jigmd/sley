import asyncio
import threading

from sley import Context, Flow, node
from utils import stream_llm


@node
def stream_answer(context: Context) -> None:
    interrupted = threading.Event()

    def wait_for_enter() -> None:
        input("Press ENTER at any time to interrupt streaming...\n")
        interrupted.set()

    listener = threading.Thread(target=wait_for_enter)
    listener.start()
    try:
        for chunk in stream_llm(context.state["prompt"]):
            if interrupted.is_set():
                print("User interrupted streaming.")
                break
            text = chunk.choices[0].delta.content
            if text:
                print(text, end="", flush=True)
    finally:
        interrupted.set()
        listener.join()


streaming_flow = Flow(stream_answer)


async def main() -> None:
    await streaming_flow.run({"prompt": "What's the meaning of life?"})


if __name__ == "__main__":
    asyncio.run(main())
