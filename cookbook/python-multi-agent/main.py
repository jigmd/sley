import asyncio

from sley import Context, Flow, node
from utils import call_llm


@node
async def hinter(context: Context) -> None:
    guess = await context.state["hinter_queue"].get()
    if guess == "GAME_OVER":
        return

    prompt = (
        f"Generate hint for '{context.state['target_word']}'\n"
        f"Forbidden words: {context.state['forbidden_words']}\n"
        f"Previous wrong guesses: {context.state['past_guesses']}\n"
        "Use at most 5 words."
    )
    hint = await call_llm(prompt)
    print(f"\nHinter: Here's your hint - {hint}")
    await context.state["guesser_queue"].put(hint)
    context.emit("continue")


@node
async def guesser(context: Context) -> None:
    hint = await context.state["guesser_queue"].get()
    prompt = (
        f"Given hint: {hint}, past wrong guesses: {context.state['past_guesses']}, "
        "make a new guess. Directly reply a single word:"
    )
    guess = await call_llm(prompt)
    print(f"Guesser: I guess it's - {guess}")

    if guess.lower() == context.state["target_word"].lower():
        print("Game Over - Correct guess!")
        await context.state["hinter_queue"].put("GAME_OVER")
        return

    context.state["past_guesses"].append(guess)
    await context.state["hinter_queue"].put(guess)
    context.emit("continue")


hinter.link(hinter, "continue")
guesser.link(guesser, "continue")
hinter_flow = Flow(hinter, max_activations=100)
guesser_flow = Flow(guesser, max_activations=100)


async def main() -> None:
    shared_channels = {
        "target_word": "nostalgic",
        "forbidden_words": ["memory", "past", "remember", "feeling", "longing"],
        "past_guesses": [],
        "hinter_queue": asyncio.Queue(),
        "guesser_queue": asyncio.Queue(),
    }
    print("=========== Taboo Game Starting! ===========")
    print(f"Target word: {shared_channels['target_word']}")
    print(f"Forbidden words: {shared_channels['forbidden_words']}")
    print("============================================")

    await shared_channels["hinter_queue"].put("")
    # Each run copies the top-level map; the nested queues are deliberately shared.
    await asyncio.gather(
        hinter_flow.run(shared_channels),
        guesser_flow.run(shared_channels),
    )
    print("=========== Game Complete! ===========")


if __name__ == "__main__":
    asyncio.run(main())
