from app.chunking import chunk_segments
from app.ocr import Segment


def seg(number, text, label=None):
    return Segment(number, label or f"Page {number}", text, "text")


def test_short_text_is_one_chunk():
    (chunk,) = chunk_segments([seg(1, "A short note about refunds.")])
    assert chunk.text == "A short note about refunds."
    assert (chunk.index, chunk.segment_number, chunk.label) == (0, 1, "Page 1")


def test_long_text_is_split_and_no_chunk_exceeds_the_target():
    text = " ".join(f"Sentence number {i} is right here." for i in range(300))
    chunks = chunk_segments([seg(1, text)], target_chars=300, overlap_chars=60)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_every_word_survives_chunking():
    text = " ".join(f"Sentence number {i} is right here." for i in range(120))
    chunks = chunk_segments([seg(1, text)], target_chars=300, overlap_chars=60)
    original = set(text.split())
    assert original <= {w for c in chunks for w in c.text.split()}


def test_consecutive_chunks_overlap():
    text = " ".join(f"Sentence number {i} is right here." for i in range(120))
    chunks = chunk_segments([seg(1, text)], target_chars=300, overlap_chars=60)
    for before, after in zip(chunks, chunks[1:]):
        assert after.text[:20] in before.text[-90:]


def test_chunks_never_cross_a_page_boundary_and_keep_their_label():
    segments = [seg(1, "Alpha " * 400), seg(2, "Beta " * 400)]
    chunks = chunk_segments(segments, target_chars=500, overlap_chars=50)
    for c in chunks:
        assert ("Alpha" in c.text) != ("Beta" in c.text)
        assert c.label == f"Page {c.segment_number}"
    assert {c.segment_number for c in chunks} == {1, 2}
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_a_single_enormous_word_is_cut_hard():
    chunks = chunk_segments([seg(1, "x" * 5000)], target_chars=1000, overlap_chars=100)
    assert len(chunks) >= 5
    assert all(len(c.text) <= 1000 for c in chunks)


def test_blank_segments_produce_no_chunks():
    assert chunk_segments([seg(1, "   \n\n  "), seg(2, "")]) == []


def test_chunking_is_deterministic():
    text = "One. Two sentences here. And a third one follows. " * 100
    assert chunk_segments([seg(1, text)]) == chunk_segments([seg(1, text)])
