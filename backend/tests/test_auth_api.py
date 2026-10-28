"""Sign-in and privacy: who can call the API, and who can see which documents."""
from app.auth import AuthError, AuthUnavailable, Identity, TokenVerifier, get_token_verifier
from app.main import app
from app.qa import Answer, Answerer, get_answerer

try:
    from tests.helpers import make_docx
except ImportError:  # tests/ is not a package here
    from helpers import make_docx

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

PEOPLE = {
    "token-alice": Identity("oid-alice", "alice@example.com", "Alice"),
    "token-bob": Identity("oid-bob", "bob@example.com", "Bob"),
}


class FakeVerifier(TokenVerifier):
    def verify(self, token):
        if token == "token-down":
            raise AuthUnavailable("The sign-in service could not be reached.")
        if token == "token-noscope":
            raise AuthError("This token does not allow access to DocMind.", status_code=403)
        if token not in PEOPLE:
            raise AuthError("The sign-in token is not valid.")
        return PEOPLE[token]


class CountingAnswerer(Answerer):
    def __init__(self):
        self.calls = 0

    def answer(self, question, passages):
        self.calls += 1
        return Answer("Found it [1].", True, [1])


def as_(person):
    return {"Authorization": f"Bearer token-{person}"}


def sign_in_required(client):
    app.dependency_overrides[get_token_verifier] = lambda: FakeVerifier()
    return client


def add_document(client, person, filename, text):
    upload = client.post(
        "/documents/upload",
        files={"file": (filename, make_docx([text]), DOCX)},
        headers=as_(person),
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]
    assert client.post(f"/documents/{document_id}/process", headers=as_(person)).status_code == 200
    assert client.post(f"/documents/{document_id}/index", headers=as_(person)).status_code == 200
    return document_id


# ---- who may call ---------------------------------------------------------------


def test_every_endpoint_but_health_needs_a_token(client):
    sign_in_required(client)
    assert client.get("/health").status_code == 200
    calls = [
        client.get("/me"),
        client.get("/documents"),
        client.get("/documents/abc"),
        client.get("/documents/abc/text"),
        client.post("/documents/abc/process"),
        client.post("/documents/abc/index"),
        client.delete("/documents/abc"),
        client.post("/search", json={"query": "x"}),
        client.post("/ask", json={"question": "x"}),
        client.post("/documents/upload", files={"file": ("a.docx", b"x", DOCX)}),
    ]
    assert [c.status_code for c in calls] == [401] * len(calls)
    assert all(c.headers["www-authenticate"] == "Bearer" for c in calls)


def test_a_bad_token_is_a_401_and_a_token_without_scope_is_a_403(client):
    sign_in_required(client)
    bad = client.get("/documents", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401
    assert "not valid" in bad.json()["detail"]
    scope = client.get("/documents", headers={"Authorization": "Bearer token-noscope"})
    assert scope.status_code == 403


def test_a_different_authorization_scheme_does_not_count(client):
    sign_in_required(client)
    assert client.get("/documents", headers={"Authorization": "Basic abc"}).status_code == 401


def test_an_unreachable_sign_in_service_is_a_503(client):
    sign_in_required(client)
    response = client.get("/documents", headers={"Authorization": "Bearer token-down"})
    assert response.status_code == 503


def test_me_says_who_you_are(client):
    sign_in_required(client)
    body = client.get("/me", headers=as_("alice")).json()
    assert body == {"email": "alice@example.com", "name": "Alice"}


def test_without_a_login_requirement_everyone_is_one_local_developer(client):
    assert client.get("/me").json() == {"email": "dev@localhost", "name": "Local developer"}


# ---- first sign-in --------------------------------------------------------------


def test_first_sign_in_creates_one_user_and_one_private_workspace(client, session_factory):
    from sqlalchemy import select

    from app.models import User, Workspace

    sign_in_required(client)
    for _ in range(3):
        assert client.get("/documents", headers=as_("alice")).status_code == 200

    with session_factory() as db:
        users = db.scalars(select(User).where(User.external_id == "oid-alice")).all()
        assert len(users) == 1
        assert users[0].display_name == "Alice"
        owned = db.scalars(select(Workspace).where(Workspace.owner_id == users[0].id)).all()
        assert len(owned) == 1


def test_an_email_already_in_use_does_not_block_a_new_person(client):
    sign_in_required(client)
    PEOPLE["token-twin"] = Identity("oid-twin", "alice@example.com", "Alice Twin")
    try:
        assert client.get("/me", headers=as_("alice")).status_code == 200
        assert client.get("/me", headers={"Authorization": "Bearer token-twin"}).status_code == 200
    finally:
        del PEOPLE["token-twin"]


# ---- privacy --------------------------------------------------------------------


def test_people_only_see_their_own_documents(client):
    sign_in_required(client)
    add_document(client, "alice", "alice.docx", "Alice keeps her salary notes here.")
    add_document(client, "bob", "bob.docx", "Bob keeps his travel plans here.")

    alice = client.get("/documents", headers=as_("alice")).json()
    bob = client.get("/documents", headers=as_("bob")).json()
    assert [d["filename"] for d in alice] == ["alice.docx"]
    assert [d["filename"] for d in bob] == ["bob.docx"]


def test_someone_elses_document_looks_like_it_does_not_exist(client, storage):
    sign_in_required(client)
    theirs = add_document(client, "alice", "alice.docx", "Alice keeps her salary notes here.")

    attempts = [
        client.get(f"/documents/{theirs}", headers=as_("bob")),
        client.get(f"/documents/{theirs}/text", headers=as_("bob")),
        client.post(f"/documents/{theirs}/process", headers=as_("bob")),
        client.post(f"/documents/{theirs}/index", headers=as_("bob")),
        client.delete(f"/documents/{theirs}", headers=as_("bob")),
    ]
    assert [a.status_code for a in attempts] == [404] * 5
    # Nothing was touched
    assert client.get(f"/documents/{theirs}", headers=as_("alice")).status_code == 200
    assert len(storage.list_files()) == 1


def test_search_never_crosses_between_people(client):
    sign_in_required(client)
    add_document(client, "alice", "alice.docx", "Confidential salary negotiation notes.")

    mine = client.post("/search", json={"query": "salary negotiation"}, headers=as_("alice"))
    theirs = client.post("/search", json={"query": "salary negotiation"}, headers=as_("bob"))
    assert [h["filename"] for h in mine.json()] == ["alice.docx"]
    assert theirs.json() == []


def test_searching_for_a_document_id_that_is_not_yours_finds_nothing(client):
    sign_in_required(client)
    theirs = add_document(client, "alice", "alice.docx", "Confidential salary negotiation notes.")
    response = client.post(
        "/search",
        json={"query": "salary negotiation", "document_id": theirs},
        headers=as_("bob"),
    )
    assert response.json() == []


def test_questions_never_use_someone_elses_documents(client):
    sign_in_required(client)
    counting = CountingAnswerer()
    app.dependency_overrides[get_answerer] = lambda: counting
    add_document(client, "alice", "alice.docx", "Confidential salary negotiation notes.")

    bobs = client.post(
        "/ask", json={"question": "salary negotiation"}, headers=as_("bob")
    ).json()
    assert bobs["found"] is False and bobs["sources"] == []
    assert counting.calls == 0  # nothing of Alice's was ever handed to the model

    alices = client.post(
        "/ask", json={"question": "salary negotiation"}, headers=as_("alice")
    ).json()
    assert alices["found"] is True
    assert alices["sources"][0]["filename"] == "alice.docx"


def test_deleting_your_own_document_leaves_the_other_persons_alone(client):
    sign_in_required(client)
    mine = add_document(client, "alice", "alice.docx", "Shared words about quarterly planning.")
    add_document(client, "bob", "bob.docx", "Shared words about quarterly planning.")

    assert client.delete(f"/documents/{mine}", headers=as_("alice")).status_code == 204
    assert client.get("/documents", headers=as_("alice")).json() == []
    bobs = client.post("/search", json={"query": "quarterly planning"}, headers=as_("bob")).json()
    assert [h["filename"] for h in bobs] == ["bob.docx"]


def test_documents_remember_who_uploaded_them(client, session_factory):
    from app.models import Document, User
    from sqlalchemy import select

    sign_in_required(client)
    document_id = add_document(client, "alice", "alice.docx", "Some notes.")
    with session_factory() as db:
        uploader = db.get(Document, document_id).uploaded_by
        assert db.get(User, uploader).external_id == "oid-alice"
