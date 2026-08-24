import base64
import io

import pymupdf
from PIL import Image


def pdf_to_images(pdf_path, max_size=2000):
    document = pymupdf.open(pdf_path)
    images = []
    try:
        for page_number, page in enumerate(document, start=1):
            pix = page.get_pixmap()
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                size = tuple(int(dimension * ratio) for dimension in image.size)
                image = image.resize(size, Image.Resampling.LANCZOS)
            images.append((image, page_number))
    finally:
        document.close()
    return images


def image_to_base64(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
