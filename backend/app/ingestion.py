"""
Handles PDF and image inputs.

- Text-based PDFs: extracted directly with PyMuPDF (fast, free, no API call).
- Scanned/image-only PDFs: rendered page-by-page and described via a
  dedicated Groq vision model, capped at MAX_VISION_PAGES.
- Raw images: sent directly to the Groq vision model.
"""

import base64
import fitz  # PyMuPDF

from .clients import get_client

MAX_VISION_PAGES = 5  # cap scanned-PDF pages sent to the vision model
MIN_TEXT_LENGTH = 50  # below this, treat the PDF as scanned/image-only
MAX_EXTRACTED_CHARS = 28_000  # keep attachment context within a useful, bounded budget


def _cap_extracted_text(text: str) -> str:
    """Avoid allowing a long attachment to crowd out the actual decision prompt."""
    if len(text) <= MAX_EXTRACTED_CHARS:
        return text
    return (
        text[:MAX_EXTRACTED_CHARS]
        + "\n\n[Attachment text truncated after 28,000 characters.]"
    )


def extract_pdf_text(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc).strip()
    finally:
        doc.close()


async def describe_image(file_bytes: bytes, mime_type: str = "image/png") -> str:
    # Use a dedicated Groq vision model since the Chairman is now text-only
    client = get_client("groq")
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    resp = await client.chat.completions.create(
        model="llama-3.2-90b-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcribe all text in this image verbatim. "
                            "If there is no readable text, describe the image's "
                            "key visual content factually and concisely."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            }
        ],
        timeout=60,
    )
    return resp.choices[0].message.content


async def extract_pdf_or_image_text(filename: str, file_bytes: bytes) -> str:
    lower = filename.lower()

    if lower.endswith(".pdf"):
        text = extract_pdf_text(file_bytes)
        if len(text) >= MIN_TEXT_LENGTH:
            return _cap_extracted_text(text)

        # Scanned PDF: render pages to images and describe via vision model
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            descriptions = []
            for i, page in enumerate(doc):
                if i >= MAX_VISION_PAGES:
                    descriptions.append(
                        f"[Note: PDF has more than {MAX_VISION_PAGES} pages; "
                        f"only the first {MAX_VISION_PAGES} were processed.]"
                    )
                    break
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                desc = await describe_image(img_bytes, "image/png")
                descriptions.append(f"[Page {i + 1}]\n{desc}")
            return _cap_extracted_text("\n\n".join(descriptions))
        finally:
            doc.close()

    elif lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        mime = "image/png" if lower.endswith(".png") else "image/jpeg"
        return _cap_extracted_text(await describe_image(file_bytes, mime))

    else:
        raise ValueError(
            f"Unsupported file type for '{filename}'. "
            "Supported: .pdf, .png, .jpg, .jpeg, .webp"
        )