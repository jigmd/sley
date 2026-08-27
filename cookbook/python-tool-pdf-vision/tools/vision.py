import os

from PIL import Image
from tools.pdf import image_to_base64
from utils.call_llm import client


def extract_text_from_image(image: Image.Image, prompt: str) -> str:
    encoded = image_to_base64(image)
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_VISION_MODEL", "gpt-4o"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                ],
            }
        ],
    )
    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("OpenAI returned no vision result")
    return content
