import logging
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # must run before any get_client() call reads env vars

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import CouncilResult
from .council import run_council
from .ingestion import extract_pdf_or_image_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="AI Council", version="1.0.0")
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_ATTACHMENTS = 5
MAX_PROMPT_CHARS = 12_000

# Wide-open CORS for local dev / Streamlit frontend calling across origins.
# Tighten allow_origins to your deployed frontend URL before going public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=CouncilResult)
async def ask(
    prompt: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    # Keep the original field working for older clients during the transition.
    file: Optional[UploadFile] = File(None),
):
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is too long. Limit it to {MAX_PROMPT_CHARS:,} characters.",
        )

    attachments = list(files)
    if file is not None:
        attachments.append(file)

    if len(attachments) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many attachments. Add up to {MAX_ATTACHMENTS} files per decision.",
        )

    context = None
    if attachments:
        try:
            extracted_attachments = []
            total_bytes = 0
            for index, attachment in enumerate(attachments, start=1):
                file_bytes = await attachment.read()
                file_size = len(file_bytes)
                if file_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="An attachment is too large. The maximum size is 12 MB per file.",
                    )
                total_bytes += file_size
                if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="The attachments are too large together. The maximum combined size is 30 MB.",
                    )

                filename = attachment.filename or f"attachment-{index}"
                extracted_text = await extract_pdf_or_image_text(filename, file_bytes)
                extracted_attachments.append(
                    f"[Attachment {index}: {filename}]\n{extracted_text}"
                )

            context = "\n\n".join(extracted_attachments)
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("File processing failed")
            raise HTTPException(status_code=502, detail=f"Failed to process file: {e}")

    try:
        result = await run_council(prompt, context=context)
    except Exception as e:
        logger.exception("Council run failed")
        raise HTTPException(status_code=502, detail=str(e))

    return result
