import asyncio

from caskada import Context, Flow, node
from utils import call_llm


@node
def chat(context: Context) -> None:
    messages = context.state.setdefault("messages", [])
    if not messages:
        print("Welcome to the chat! Type 'exit' to end the conversation.")

    user_input = input("\nYou: ")
    if user_input.lower() == "exit":
        print("\nGoodbye!")
        return

    messages.append({"role": "user", "content": user_input})
    response = call_llm(messages)
    print(f"\nAssistant: {response}")
    messages.append({"role": "assistant", "content": response})

    # The named self-link starts the next turn with the same run state.
    context.emit("continue")


chat.link(chat, "continue")
chat_flow = Flow(chat)


async def main() -> None:
    await chat_flow.run({})


if __name__ == "__main__":
    asyncio.run(main())
