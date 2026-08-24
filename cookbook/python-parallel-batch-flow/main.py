import asyncio
import time
from pathlib import Path

from flow import create_flows


def image_paths() -> list[str]:
    paths = sorted(str(path) for path in Path("images").glob("*.*"))
    if not paths:
        raise ValueError("No images found in the images directory")
    print(f"Found {len(paths)} images:")
    for path in paths:
        print(f"- {path}")
    return paths


async def timed_run(label: str, flow, initial_state: dict) -> float:
    print(f"\nRunning {label} flow...")
    started = time.perf_counter()
    await flow.run(initial_state)
    return time.perf_counter() - started


async def main() -> None:
    print("Parallel Image Processor")
    print("-" * 30)
    state = {"images": image_paths()}
    sequential, parallel = create_flows()

    sequential_time = await timed_run("sequential", sequential, state)
    parallel_time = await timed_run("parallel", parallel, state)

    print("\nTiming Results:")
    print(f"Sequential batch processing: {sequential_time:.2f} seconds")
    print(f"Parallel batch processing: {parallel_time:.2f} seconds")
    print(f"Speedup: {sequential_time / parallel_time:.2f}x")
    print("\nProcessing complete! Check the output/ directory for results.")


if __name__ == "__main__":
    asyncio.run(main())
