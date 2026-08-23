import asyncio
import time
from pathlib import Path

from sley import Context, Flow, node
from utils import call_llm


@node
def dispatch(context: Context) -> None:
    for language in context.state["languages"]:
        context.emit("translate", (context.state["text"], language))


@node
def translate(context: Context) -> None:
    text, language = context.input
    prompt = f"""
Please translate the following markdown into {language}.
Keep the original formatting, links, and code blocks.
Return only the translated text.

{text}
"""
    translation = call_llm(prompt)

    output = Path(context.state["output_dir"])
    output.mkdir(exist_ok=True)
    filename = output / f"README_{language.upper()}.md"
    filename.write_text(translation, encoding="utf-8")
    print(f"Saved translation to {filename}")
    context.end()


dispatch.link(translate, "translate")
translation_flow = Flow(dispatch)


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

    print(f"Starting sequential translation into {len(languages)} languages...")
    started = time.perf_counter()
    await translation_flow.run(initial_state)
    print(
        f"\nTotal sequential translation time: {time.perf_counter() - started:.4f} seconds"
    )
    print("\n=== Translation Complete ===")
    print("Translations saved to: translations")


if __name__ == "__main__":
    asyncio.run(main())
