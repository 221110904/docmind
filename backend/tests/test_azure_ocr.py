import base64
import io
import json
import re
from types import SimpleNamespace
from unittest import mock

import pytest
import requests
import urllib3
from azure.core.exceptions import HttpResponseError
from pypdf import PdfReader

from app.ocr import AzureDocumentIntelligenceOcr, OcrError, build_sub_pdf
from tests import helpers as h


class FakeClient:
    """Stands in for DocumentIntelligenceClient and records every request."""

    def __init__(self, error=None):
        self.bodies = []
        self.error = error

    def begin_analyze_document(self, model_id, body, **kwargs):
        assert model_id == "prebuilt-read"
        if self.error:
            raise self.error
        self.bodies.append(body.bytes_source)
        count = len(PdfReader(io.BytesIO(body.bytes_source)).pages) if body.bytes_source[:4] == b"%PDF" else 1
        pages = [
            SimpleNamespace(
                page_number=i + 1,
                lines=[SimpleNamespace(content=f"line from sub-page {i + 1}")],
            )
            for i in range(count)
        ]
        return SimpleNamespace(result=lambda: SimpleNamespace(pages=pages))


def engine(client, **kwargs):
    return AzureDocumentIntelligenceOcr("https://x", "key", client=client, **kwargs)


def page_counts(client):
    return [len(PdfReader(io.BytesIO(b)).pages) for b in client.bodies]


def test_scanned_pages_are_sent_in_batches_of_two_and_numbers_are_restored():
    client = FakeClient()
    segments = engine(client).read(h.make_blank_pdf(6), "application/pdf", pages=[2, 4, 5])
    assert page_counts(client) == [2, 1]  # [2, 4] then [5]
    assert [s.number for s in segments] == [2, 4, 5]
    assert [s.label for s in segments] == ["Page 2", "Page 4", "Page 5"]
    assert all(s.source == "ocr" for s in segments)
    assert segments[1].text == "line from sub-page 2"  # 2nd page of the 1st batch


def test_five_page_scan_needs_three_requests_on_the_free_tier():
    client = FakeClient()
    engine(client).read(h.make_blank_pdf(5), "application/pdf", pages=[1, 2, 3, 4, 5])
    assert page_counts(client) == [2, 2, 1]


def test_oversize_batches_are_split_into_smaller_requests():
    reader = PdfReader(io.BytesIO(h.make_blank_pdf(4)))
    one = len(build_sub_pdf(reader, [1]))
    two = len(build_sub_pdf(reader, [1, 2]))
    assert one < two
    client = FakeClient()
    # allow a single page but not two: every batch of two has to be split
    segments = engine(client, max_request_bytes=two - 1).read(
        h.make_blank_pdf(4), "application/pdf", pages=[1, 2, 3, 4]
    )
    assert page_counts(client) == [1, 1, 1, 1]
    assert [s.number for s in segments] == [1, 2, 3, 4]


def test_single_page_over_the_limit_is_a_clear_error():
    with pytest.raises(OcrError, match="Page 1 is larger"):
        engine(FakeClient(), max_request_bytes=10).read(
            h.make_blank_pdf(1), "application/pdf", pages=[1]
        )


def test_image_over_the_limit_is_a_clear_error():
    with pytest.raises(OcrError, match="larger than the OCR request limit"):
        engine(FakeClient(), max_request_bytes=10).read(h.make_png(), "image/png")


def test_image_text_is_returned_as_one_segment():
    (segment,) = engine(FakeClient()).read(h.make_png(), "image/png")
    assert (segment.number, segment.label, segment.source) == (1, "Image", "ocr")


@pytest.mark.parametrize(
    "status, expected",
    [(429, "quota"), (401, "credentials"), (500, "OCR service error (500)")],
)
def test_service_errors_become_readable_ocr_errors(status, expected):
    response = SimpleNamespace(status_code=status, reason="x", headers={})
    error = HttpResponseError(message="boom", response=response)
    error.status_code = status
    with pytest.raises(OcrError, match=re.escape(expected)):
        engine(FakeClient(error=error)).read(h.make_png(), "image/png")


def test_real_sdk_builds_the_correct_request_and_parses_the_reply():
    """Runs the genuine Azure SDK against intercepted (fake) network calls."""
    seen = []
    payload = {
        "status": "succeeded",
        "createdDateTime": "2026-01-01T00:00:00Z",
        "lastUpdatedDateTime": "2026-01-01T00:00:01Z",
        "analyzeResult": {
            "apiVersion": "2024-11-30", "modelId": "prebuilt-read",
            "stringIndexType": "textElements", "content": "Hello\nWorld",
            "pages": [{
                "pageNumber": 1, "angle": 0, "width": 8.5, "height": 11, "unit": "inch",
                "spans": [{"offset": 0, "length": 11}],
                "lines": [
                    {"content": "Hello", "polygon": [0, 0, 1, 0, 1, 1, 0, 1], "spans": [{"offset": 0, "length": 5}]},
                    {"content": "World", "polygon": [0, 0, 1, 0, 1, 1, 0, 1], "spans": [{"offset": 6, "length": 5}]},
                ],
            }],
        },
    }

    def reply(status, body=b"", headers=None):
        r = requests.Response()
        r.status_code = status
        r.raw = urllib3.HTTPResponse(body=io.BytesIO(body), status=status, preload_content=False)
        r.headers.update(headers or {})
        return r

    def fake_request(self, method, url, **kwargs):
        seen.append((method, url, kwargs))
        if method.upper() == "POST":
            location = (
                "https://fake.cognitiveservices.azure.com/documentintelligence/"
                "documentModels/prebuilt-read/analyzeResults/abc?api-version=2024-11-30"
            )
            return reply(202, headers={"Operation-Location": location})
        return reply(200, json.dumps(payload).encode(), {"Content-Type": "application/json"})

    image = h.make_png()
    with mock.patch("requests.Session.request", fake_request):
        ocr = AzureDocumentIntelligenceOcr("https://fake.cognitiveservices.azure.com", "key")
        (segment,) = ocr.read(image, "image/png")

    method, url, kwargs = seen[0]
    assert method.upper() == "POST"
    assert "documentModels/prebuilt-read:analyze" in url
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert base64.b64decode(json.loads(kwargs["data"])["base64Source"]) == image
    assert segment.text == "Hello\nWorld"
