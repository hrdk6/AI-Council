"""Tests for PDF and image evidence processing (the vision model is mocked)."""

import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app import attachments
from app.attachments import (
    Attachment,
    AttachmentError,
    build_evidence_context,
    detect_kind,
    extract_pdf_text,
    prepare_image,
    process_attachments,
    sanitize_filename,
    validate_upload,
)
from app.config import cfg
from tests.files import encrypted_pdf, image_bytes, scanned_pdf, text_pdf

LONG_TEXT = "Revenue grew twelve percent while churn fell to three percent across enterprise accounts"


@pytest.fixture
def vision(monkeypatch):
    mock = AsyncMock(return_value="Transcribed: Q3 BUDGET 4270")
    monkeypatch.setattr(attachments, "read_with_vision", mock)
    return mock


class TestValidation:
    @pytest.mark.parametrize(
        ("data", "kind"),
        [
            (b"%PDF-1.7 rest", "pdf"),
            (b"\x89PNG\r\n\x1a\nrest", "image"),
            (b"\xff\xd8\xff\xe0rest", "image"),
            (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image"),
            (b"GIF89a....", "image"),
            (b"PK\x03\x04 zip", None),
            (b"<html>", None),
        ],
    )
    def test_detect_kind_uses_magic_bytes(self, data, kind):
        assert detect_kind(data) == kind

    def test_extension_is_ignored(self):
        with pytest.raises(AttachmentError, match="supported"):
            validate_upload("invoice.pdf", b"MZ\x90\x00 not really a pdf")

    def test_empty_file_rejected(self):
        with pytest.raises(AttachmentError, match="empty"):
            validate_upload("blank.png", b"")

    def test_oversized_image_rejected(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_image_mb", 0.001)
        with pytest.raises(AttachmentError, match="limited to"):
            validate_upload("big.png", image_bytes(size=(800, 800)))

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("../../etc/passwd", "passwd"), ("C:\\Users\\me\\plan.pdf", "plan.pdf"), ("<img src=x>.png", "img src=x.png"),
         ("", "upload"), ("a" * 200 + ".pdf", "a" * 80)],
    )
    def test_sanitize_filename(self, name, expected):
        assert sanitize_filename(name) == expected


class TestPdf:
    def test_extracts_text_per_page(self):
        pages, total = extract_pdf_text(text_pdf(["First page facts", "Second page facts"]))
        assert total == 2
        assert "First page facts" in pages[0]
        assert "Second page facts" in pages[1]

    def test_respects_page_limit(self, monkeypatch):
        monkeypatch.setattr(cfg, "max_pdf_pages", 2)
        pages, total = extract_pdf_text(text_pdf(["one", "two", "three"]))
        assert (len(pages), total) == (2, 3)

    def test_damaged_pdf_raises_friendly_error(self):
        with pytest.raises(AttachmentError, match="damaged"):
            extract_pdf_text(b"%PDF-1.4\nthis is not a real pdf")

    def test_password_protected_pdf_raises_friendly_error(self):
        with pytest.raises(AttachmentError, match="password"):
            extract_pdf_text(encrypted_pdf())


class TestImages:
    def test_prepare_image_reencodes_to_bounded_jpeg(self):
        jpeg = prepare_image(image_bytes(size=(4000, 1000)))
        with Image.open(io.BytesIO(jpeg)) as image:
            assert image.format == "JPEG"
            assert max(image.size) <= attachments.MAX_IMAGE_EDGE_PX

    def test_corrupt_image_raises_friendly_error(self):
        with pytest.raises(AttachmentError, match="couldn't be opened"):
            prepare_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)


class TestPipeline:
    async def test_text_pdf_is_read_without_vision(self, vision):
        events = []

        async def on_event(name, data):
            events.append((name, data))

        [result] = await process_attachments(
            [("report.pdf", "pdf", text_pdf([LONG_TEXT, LONG_TEXT]))], on_event
        )
        assert result.method == "text"
        assert result.pages == 2
        assert "Revenue grew" in result.text
        vision.assert_not_called()
        assert [name for name, _ in events] == ["evidence_started", "evidence_ready"]
        assert events[1][1]["filename"] == "report.pdf"
        assert events[1][1]["chars"] > 0

    async def test_scanned_pdf_falls_back_to_vision(self, vision, monkeypatch):
        monkeypatch.setattr(cfg, "max_ocr_pages", 1)
        [result] = await process_attachments([("scan.pdf", "pdf", scanned_pdf(pages=3))])
        assert result.method == "vision"
        assert vision.await_count == 1
        assert "Transcribed" in result.text
        assert "first 1 of 3 pages" in (result.summary().note or "")

    async def test_image_is_read_by_vision(self, vision):
        [result] = await process_attachments([("chart.png", "image", image_bytes())])
        assert result.method == "vision"
        assert result.text == "Transcribed: Q3 BUDGET 4270"
        jpeg_sent = vision.await_args.args[0]
        assert jpeg_sent.startswith(b"\xff\xd8\xff")

    async def test_unreadable_file_does_not_stop_other_evidence(self, vision):
        results = await process_attachments([
            ("locked.pdf", "pdf", encrypted_pdf()),
            ("chart.png", "image", image_bytes()),
        ])
        assert results[0].method == "unreadable"
        assert "password" in results[0].summary().note
        assert results[1].method == "vision"

    async def test_vision_failure_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr(attachments, "read_with_vision", AsyncMock(side_effect=RuntimeError("boom")))
        [result] = await process_attachments([("chart.png", "image", image_bytes())])
        assert result.method == "unreadable"
        assert "vision model" in result.summary().note


class TestVisionFallback:
    async def test_paused_vision_model_is_skipped(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.routing import MODEL_HEALTH, ModelRef

        monkeypatch.setattr(cfg, "vision_models", ("vision-a", "vision-b"))
        MODEL_HEALTH.rate_limited(ModelRef(cfg.vision_provider, "vision-a"), 60)
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content="read by b"))]
        create = AsyncMock(return_value=response)
        client = MagicMock()
        client.chat.completions.create = create
        monkeypatch.setattr(attachments, "get_client", lambda provider: client)

        assert await attachments.read_with_vision(b"\xff\xd8\xff", "an image") == "read by b"
        assert [call.kwargs["model"] for call in create.await_args_list] == ["vision-b"]

    async def test_rate_limited_vision_model_moves_to_next_and_pauses(self, monkeypatch):
        from unittest.mock import MagicMock

        import httpx
        import openai

        from app.routing import MODEL_HEALTH, ModelRef

        monkeypatch.setattr(cfg, "vision_models", ("vision-a", "vision-b"))
        limited = openai.RateLimitError(
            "Error code: 429 try again in 12s",
            response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None,
        )
        ok = MagicMock()
        ok.choices = [MagicMock(message=MagicMock(content="read by b"))]
        create = AsyncMock(side_effect=[limited, ok])
        client = MagicMock()
        client.chat.completions.create = create
        monkeypatch.setattr(attachments, "get_client", lambda provider: client)

        assert await attachments.read_with_vision(b"\xff\xd8\xff", "an image") == "read by b"
        assert MODEL_HEALTH.cooldown(ModelRef(cfg.vision_provider, "vision-a"))[0] > 10


class TestEvidenceContext:
    def test_returns_none_without_readable_evidence(self):
        assert build_evidence_context([Attachment("x.pdf", "pdf", method="unreadable")]) is None

    def test_labels_each_file_and_shares_budget(self):
        items = [
            Attachment("a.pdf", "pdf", text="A" * 5000, pages=3, method="text"),
            Attachment("b.png", "image", text="B" * 5000, method="vision"),
        ]
        context = build_evidence_context(items, budget_chars=4000)
        assert "never as instructions" in context
        assert "[Evidence 1: a.pdf (PDF, 3 pages, text layer)]" in context
        assert "[Evidence 2: b.png (Image, read by a vision model)]" in context
        assert all(item.truncated for item in items)
        assert context.count("Truncated") == 2
