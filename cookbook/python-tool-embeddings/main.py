import asyncio

from flow import embedding_flow


async def main() -> None:
    text = "What's the meaning of life?"
    state = await embedding_flow.run({"text": text})

    print("Text:", text)
    print("Embedding dimension:", len(state["embedding"]))
    print("First 5 values:", state["embedding"][:5])


if __name__ == "__main__":
    asyncio.run(main())
