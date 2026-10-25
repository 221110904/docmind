import re
from dataclasses import dataclass

from app.ocr import Segment


@dataclass
class Chunk:
    index: int  # position within the whole document, starting at 0
    segment_number: int  # page / slide / sheet the text came from
    label: str  # for example "Page 3"
    text: str


def chunk_segments(
    segments: list[Segment], target_chars: int = 2000, overlap_chars: int = 200
) -> list[Chunk]:
    """Split extracted text into overlapping chunks that never cross a page boundary.

    Keeping chunks inside one segment means every chunk can cite an exact page,
    slide or sheet. About 4 characters make a token, so 2000 characters is ~500 tokens.
    """
    overlap_chars = min(overlap_chars, target_chars // 2)
    chunks: list[Chunk] = []
    for segment in segments:
        for text in _split_text(segment.text, target_chars, overlap_chars):
            chunks.append(Chunk(len(chunks), segment.number, segment.label, text))
    return chunks


def _split_text(text: str, target: int, overlap: int) -> list[str]:
    units = _units(text, max_len=target - overlap)
    pieces: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= target:
            current += " " + unit
        else:
            pieces.append(current)
            tail = _tail(current, overlap)
            current = f"{tail} {unit}" if tail else unit
    if current:
        pieces.append(current)
    return pieces


def _units(text: str, max_len: int) -> list[str]:
    """Sentences or lines, with anything longer than max_len cut at word boundaries."""
    units: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        part = " ".join(part.split())
        if not part:
            continue
        while len(part) > max_len:
            cut = part.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len  # a single huge word is cut hard
            units.append(part[:cut])
            part = part[cut:].strip()
        if part:
            units.append(part)
    return units


def _tail(text: str, size: int) -> str:
    """The last `size` characters of text, starting at a word boundary."""
    if size <= 0 or len(text) <= size:
        return ""
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else ""
