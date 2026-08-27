import asyncio
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from sley import Context


def dispatch(context: Context) -> None:
    filters = ("grayscale", "blur", "sepia")
    print(
        f"Processing {len(context.state['images'])} images with {len(filters)} filters..."
    )
    for image_path in context.state["images"]:
        for filter_name in filters:
            context.emit("process", {"image_path": image_path, "filter": filter_name})


def read_image(path: str):
    with Image.open(path) as source:
        return source.copy()


async def load_image(context: Context) -> None:
    job = context.input
    print(f"Loading image: {job['image_path']}")
    image = await asyncio.to_thread(read_image, job["image_path"])
    context.emit("filter", {"job": job, "image": image})


def filter_image(image, filter_name: str):
    if filter_name == "grayscale":
        return image.convert("L")
    if filter_name == "blur":
        return image.filter(ImageFilter.BLUR)
    else:
        matrix = np.array(
            [[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]]
        )
        pixels = np.clip(np.array(image).dot(matrix.T), 0, 255).astype(np.uint8)
        return Image.fromarray(pixels)


async def apply_filter(context: Context) -> None:
    job = context.input["job"]
    print(f"Applying {job['filter']} filter...")
    filtered = await asyncio.to_thread(
        filter_image, context.input["image"], job["filter"]
    )

    context.emit("save", {"job": job, "image": filtered})


def write_image(image, path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    image.save(path)


async def save_image(context: Context) -> None:
    job = context.input["job"]
    path = Path("output") / f"{Path(job['image_path']).stem}_{job['filter']}.jpg"
    await asyncio.to_thread(write_image, context.input["image"], path)
    print(f"Saved: {path}")
    context.end(path)
