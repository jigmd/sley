from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter
from sley import Context


def dispatch(context: Context) -> None:
    for image_name in ("cat.jpg", "dog.jpg", "bird.jpg"):
        for filter_name in ("grayscale", "blur", "sepia"):
            context.emit("process", {"image_name": image_name, "filter": filter_name})


def load_image(context: Context) -> None:
    job = context.input
    with Image.open(Path("images") / job["image_name"]) as source:
        image = source.copy()
    context.emit("filter", {"job": job, "image": image})


def apply_filter(context: Context) -> None:
    job = context.input["job"]
    image = context.input["image"]
    if job["filter"] == "grayscale":
        filtered = image.convert("L")
    elif job["filter"] == "blur":
        filtered = image.filter(ImageFilter.BLUR)
    else:
        grayscale = ImageEnhance.Color(image).enhance(0.3)
        filtered = ImageEnhance.Brightness(grayscale).enhance(1.2)
    context.emit("save", {"job": job, "image": filtered})


def save_image(context: Context) -> None:
    job = context.input["job"]
    output = Path("output")
    output.mkdir(exist_ok=True)
    filename = output / f"{Path(job['image_name']).stem}_{job['filter']}.jpg"
    context.input["image"].save(filename, "JPEG")
    print(f"Saved filtered image to: {filename}")
    context.end(filename)
