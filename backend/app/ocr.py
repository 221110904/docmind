from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Segment:
    """One citable piece of a document: a page, a slide, a sheet, or an image."""

    number: int  # page / slide / sheet number, starting at 1
    label: str  # for example "Page 3", "Slide 2", "Sheet: Budget"
    text: str
    source: str  # "text" (read from the file) or "ocr" (read from pixels)


class OcrUnavailable(Exception):
    """The file needs OCR but no OCR engine is configured."""


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


@lru_cache
def get_ocr() -> OcrEngine:
    # The Azure Document Intelligence engine is added once that resource exists
    return NoOcr()
