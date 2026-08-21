from pathlib import Path

from caskada import Context, node
from tools.pdf import pdf_to_images
from tools.vision import extract_text_from_image

PDF_DIR = Path(__file__).parent / "pdfs"
DEFAULT_PROMPT = "Extract all text, preserving the document's formatting."


@node
def dispatch_pdfs(context: Context) -> None:
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDF files")
    if not pdfs:
        context.end()
        return

    for path in pdfs:
        context.emit(
            "process",
            {
                "path": path,
                "prompt": context.state.get("extraction_prompt", DEFAULT_PROMPT),
            },
        )


@node
def process_pdf(context: Context) -> None:
    job = context.input
    path = job["path"]
    print(f"\nProcessing: {path.name}")

    pages = []
    for image, page_number in pdf_to_images(path):
        text = extract_text_from_image(image, job["prompt"])
        pages.append(f"=== Page {page_number} ===\n{text}")

    # Each finished PDF contributes one value to the Flow's result.outputs.
    context.end({"filename": path.name, "text": "\n\n".join(pages)})
