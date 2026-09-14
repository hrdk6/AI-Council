"""Generate real PDF and image fixtures in memory for upload tests."""

import io

from PIL import Image, ImageDraw


def text_pdf(page_texts: list[str]) -> bytes:
    """Build a minimal, valid PDF with one Helvetica text line per page."""
    count = len(page_texts)
    page_ids = [4 + 2 * index for index in range(count)]
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] /Count {count} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, text in enumerate(page_texts):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects[page_ids[index]] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[index] + 1} 0 R >>"
        )
        objects[page_ids[index] + 1] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = {}
    for object_id in sorted(objects):
        offsets[object_id] = output.tell()
        output.write(f"{object_id} 0 obj\n{objects[object_id]}\nendobj\n".encode("latin-1"))
    xref_start = output.tell()
    size = max(objects) + 1
    output.write(f"xref\n0 {size}\n0000000000 65535 f \n".encode())
    for object_id in range(1, size):
        output.write(f"{offsets[object_id]:010d} 00000 n \n".encode())
    output.write(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode())
    return output.getvalue()


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (320, 120), text: str = "Q3 BUDGET 4270") -> bytes:
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).text((10, 40), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def scanned_pdf(pages: int = 2) -> bytes:
    """An image-only PDF, like a scan: no text layer at all."""
    frames = [Image.new("RGB", (400, 300), "white") for _ in range(pages)]
    for number, frame in enumerate(frames, 1):
        ImageDraw.Draw(frame).text((20, 20), f"Scanned page {number}", fill="black")
    buffer = io.BytesIO()
    frames[0].save(buffer, format="PDF", save_all=True, append_images=frames[1:])
    return buffer.getvalue()


def encrypted_pdf() -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf(["Secret plan"]))))
    writer.encrypt(user_password="hunter2", algorithm="AES-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
