import asyncio
import time
from pathlib import Path

from caskada import Context, Flow, RetryPolicy, node
from utils import call_llm


@node
def dispatch(context: Context) -> None:
    for language in context.state["languages"]:
        context.emit("translate", (context.state["text"], language))


def save_translation(output_dir: str, language: str, translation: str) -> None:
    output = Path(output_dir)
    output.mkdir(exist_ok=True)
    filename = output / f"README_{language.upper()}.md"
    filename.write_text(translation, encoding="utf-8")
    print(f"Saved translation to {filename}")


@node(retry=RetryPolicy(max_attempts=3))
async def translate(context: Context) -> None:
    text, language = context.input
    prompt = f"""
Please translate the following markdown into {language}.
Keep the original formatting, links, and code blocks.
Return only the translated text.

{text}
"""
    translation = await call_llm(prompt)
    save_translation(context.state["output_dir"], language, translation)
    context.end()


dispatch.link(translate, "translate")
translation_flow = Flow(dispatch, concurrency=8)


async def main() -> None:
    languages = [
        "Chinese",
        "Spanish",
        "Japanese",
        "German",
        "Russian",
        "Portuguese",
        "French",
        "Korean",
    ]
    initial_state = {
        "text": Path("../../README.md").read_text(encoding="utf-8"),
        "languages": languages,
        "output_dir": "translations",
    }

    print(f"Starting parallel translation into {len(languages)} languages...")
    started = time.perf_counter()
    await translation_flow.run(initial_state)
    print(
        f"\nTotal parallel translation time: {time.perf_counter() - started:.4f} seconds"
    )
    print("\n=== Translation Complete ===")
    print("Translations saved to: translations")


if __name__ == "__main__":
    asyncio.run(main())
