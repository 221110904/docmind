from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

from app.config import settings


@dataclass
class Segment:
    """One citable piece of a document: a page, a slide, a sheet, or an image."""

    number: int  # page / slide / sheet number, starting at 1
    label: str  # for example "Page 3", "Slide 2", "Sheet: Budget"
    text: str
    source: str  # "text" (read from the file) or "ocr" (read from pixels)


class OcrUnavailable(Exception):
    """The file needs OCR but no OCR engine is configured."""


class OcrError(Exception):
    """The OCR service was reached (or should have been) but could not read the file."""


class OcrEngine(ABC):
    @abstractmethod
    def read(
        self, data: bytes, content_type: str, pages: list[int] | None = None
    ) -> list[Segment]:
        """Read text from an image or from the given pages (1-based) of a PDF."""


class NoOcr(OcrEngine):
    """Default engine: reports that OCR is not set up instead of guessing."""

    def read(self, data, content_type, pages=None):
        raise OcrUnavailable("OCR is not configured")


def build_sub_pdf(reader, pages: list[int]) -> bytes:
    """A new PDF containing only the given 1-based pages of an open PdfReader."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for number in pages:
        writer.add_page(reader.pages[number - 1])
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _describe_service_error(exc) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "OCR service rejected the credentials (check the endpoint and key)."
    if status == 429:
        return "OCR service rate limit or monthly free quota reached."
    reason = (getattr(exc, "message", None) or str(exc)).strip().splitlines()[0][:200]
    return f"OCR service error ({status}): {reason}"


class AzureDocumentIntelligenceOcr(OcrEngine):
    """Reads scans and images with Azure Document Intelligence (prebuilt-read model)."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        pages_per_request: int = 2,
        max_request_bytes: int = 4 * 1024 * 1024,
        client=None,
    ):
        if client is None:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential

            client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
        self._client = client
        self._pages_per_request = max(1, pages_per_request)
        self._max_bytes = max_request_bytes

    def read(self, data, content_type, pages=None):
        if pages is None:
            return self._read_image(data)
        return self._read_pdf_pages(data, pages)

    def _read_image(self, data: bytes) -> list[Segment]:
        if len(data) > self._max_bytes:
            raise OcrError(
                f"The image is larger than the OCR request limit "
                f"({self._max_bytes // (1024 * 1024)} MB)."
            )
        pages = self._analyze(data)
        text = _page_text(pages[0]) if pages else ""
        return [Segment(1, "Image", text, "ocr")] if text.strip() else []

    def _read_pdf_pages(self, data: bytes, pages: list[int]) -> list[Segment]:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        size = self._pages_per_request
        queue = [pages[i : i + size] for i in range(0, len(pages), size)]
        segments: list[Segment] = []
        while queue:
            batch = queue.pop(0)
            body = build_sub_pdf(reader, batch)
            if len(body) > self._max_bytes:
                if len(batch) == 1:
                    raise OcrError(
                        f"Page {batch[0]} is larger than the OCR request limit "
                        f"({self._max_bytes // (1024 * 1024)} MB)."
                    )
                middle = len(batch) // 2  # too big: retry as two smaller requests
                queue[0:0] = [batch[:middle], batch[middle:]]
                continue
            for result_page in self._analyze(body):
                index = result_page.page_number - 1
                if not 0 <= index < len(batch):
                    continue
                text = _page_text(result_page)
                if text.strip():
                    number = batch[index]
                    segments.append(Segment(number, f"Page {number}", text, "ocr"))
        return sorted(segments, key=lambda s: s.number)

    def _analyze(self, body: bytes) -> list:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.exceptions import HttpResponseError

        try:
            poller = self._client.begin_analyze_document(
                "prebuilt-read",
                AnalyzeDocumentRequest(bytes_source=body),
                polling_interval=1,
            )
            result = poller.result()
        except HttpResponseError as exc:
            raise OcrError(_describe_service_error(exc)) from exc
        return sorted(result.pages or [], key=lambda p: p.page_number)


def _page_text(page) -> str:
    return "\n".join(line.content for line in (page.lines or []))


@lru_cache
def get_ocr() -> OcrEngine:
    if settings.ocr_backend == "azure":
        if not (settings.document_intelligence_endpoint and settings.document_intelligence_key):
            raise RuntimeError(
                "OCR_BACKEND=azure but DOCUMENT_INTELLIGENCE_ENDPOINT or "
                "DOCUMENT_INTELLIGENCE_KEY is empty"
            )
        return AzureDocumentIntelligenceOcr(
            settings.document_intelligence_endpoint,
            settings.document_intelligence_key,
            pages_per_request=settings.ocr_pages_per_request,
            max_request_bytes=settings.ocr_max_request_mb * 1024 * 1024,
        )
    return NoOcr()
