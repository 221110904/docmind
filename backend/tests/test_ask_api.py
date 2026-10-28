from app.main import app
from app.qa import NOT_FOUND, Answer, Answerer, get_answerer

try:
    from tests.helpers import make_docx
except ImportError:  # tests/ is not a package here
    from helpers import make_docx

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ScriptedAnswerer(Answerer):
    """Returns a fixed answer and records the sources it was given."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def answer(self, question, passages):
        self.calls.append((question, passages))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def index_document(client, filename, paragraphs):
    upload = client.post(
        "/documents/upload", files={"file": (filename, make_docx(paragraphs), DOCX)}
    )
    assert upload.status_code in (200, 201), upload.text
    document_id = upload.json()["id"]
    assert client.post(f"/documents/{document_id}/process").status_code == 200
    assert client.post(f"/documents/{document_id}/index").status_code == 200
    return document_id


def test_ask_with_nothing_indexed_says_not_found_without_calling_the_model(client):
    scripted = ScriptedAnswerer(Answer("should not be used", True, [1]))
    app.dependency_overrides[get_answerer] = lambda: scripted
    response = client.post("/ask", json={"question": "What is the USB policy?"})
    assert response.status_code == 200
    body = response.json()
    assert (body["found"], body["answer"], body["sources"]) == (False, NOT_FOUND, [])
    assert scripted.calls == []


def test_ask_returns_the_answer_with_its_cited_sources(client):
    index_document(
        client, "audit.docx", ["Staff may use personal USB drives and external hard disks."]
    )
    scripted = ScriptedAnswerer(Answer("Yes, personal USB drives are allowed [1].", True, [1]))
    app.dependency_overrides[get_answerer] = lambda: scripted
    response = client.post("/ask", json={"question": "Can staff use personal USB drives?"})
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["answer"].endswith("[1].")
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert (source["number"], source["filename"]) == (1, "audit.docx")
    assert "USB drives" in source["content"]
    # The model was given the numbered sources and the question
    question, passages = scripted.calls[0]
    assert question == "Can staff use personal USB drives?"
    assert passages[0].number == 1


def test_ask_lists_only_the_sources_the_answer_cited(client):
    index_document(client, "a.docx", ["Personal USB drives are allowed for work files."])
    index_document(client, "b.docx", ["Personal USB drives need written approval."])
    scripted = ScriptedAnswerer(Answer("Allowed [2].", True, [2]))
    app.dependency_overrides[get_answerer] = lambda: scripted
    body = client.post("/ask", json={"question": "personal USB drives", "top_k": 5}).json()
    assert [s["number"] for s in body["sources"]] == [2]
    assert len(scripted.calls[0][1]) == 2


def test_ask_can_be_limited_to_one_document(client):
    first = index_document(client, "a.docx", ["Personal USB drives are allowed."])
    index_document(client, "b.docx", ["Personal USB drives need approval."])
    scripted = ScriptedAnswerer(Answer("ok [1]", True, [1]))
    app.dependency_overrides[get_answerer] = lambda: scripted
    client.post("/ask", json={"question": "personal USB drives", "document_id": first})
    assert {p.document_id for p in scripted.calls[0][1]} == {first}


def test_ask_with_the_local_stand_in_works_end_to_end(client):
    index_document(client, "audit.docx", ["Backups run weekly and stay in the server room."])
    body = client.post("/ask", json={"question": "How often do backups run?"}).json()
    assert body["found"] is True
    assert body["sources"][0]["filename"] == "audit.docx"


def test_answer_service_failure_is_a_502_with_a_readable_message(client):
    from app.qa import QaError

    index_document(client, "audit.docx", ["Backups run weekly."])
    app.dependency_overrides[get_answerer] = lambda: ScriptedAnswerer(
        QaError("Answer rate limit reached.")
    )
    response = client.post("/ask", json={"question": "How often do backups run?"})
    assert response.status_code == 502
    assert "rate limit" in response.json()["detail"]


def test_ask_rejects_an_empty_question(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422
