import asyncio
from pathlib import Path

import numpy as np
from caskada import Context
from PIL import Image, ImageFilter


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
    await asyncio.sleep(0.1)
    context.emit("filter", {"job": job, "image": read_image(job["image_path"])})


async def apply_filter(context: Context) -> None:
    job = context.input["job"]
    image = context.input["image"]
    print(f"Applying {job['filter']} filter...")
    await asyncio.sleep(0.1)

    if job["filter"] == "grayscale":
        filtered = image.convert("L")
    elif job["filter"] == "blur":
        filtered = image.filter(ImageFilter.BLUR)
    else:
        matrix = np.array(
            [[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]]
        )
        pixels = np.clip(np.array(image).dot(matrix.T), 0, 255).astype(np.uint8)
        filtered = Image.fromarray(pixels)

    context.emit("save", {"job": job, "image": filtered})


def write_image(image, path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    image.save(path)


async def save_image(context: Context) -> None:
    job = context.input["job"]
    path = Path("output") / f"{Path(job['image_path']).stem}_{job['filter']}.jpg"
    await asyncio.sleep(0.1)
    write_image(context.input["image"], path)
    print(f"Saved: {path}")
    context.end(path)
