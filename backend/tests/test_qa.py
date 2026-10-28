import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.qa import (
    NOT_FOUND,
    AzureOpenAIAnswerer,
    FakeAnswerer,
    Passage,
    QaError,
    build_user_message,
    parse_answer,
)


def passage(number, content="Staff may use personal USB drives.", filename="audit.docx"):
    return Passage(number, f"doc{number}", filename, "Document", 1, number - 1, content)


class StubChat:
    """Stands in for the OpenAI client and records what it was asked."""

    def __init__(self, reply=None, error=None, finish_reason="stop"):
        self.reply, self.error, self.finish_reason = reply, error, finish_reason
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.reply)
        choice = SimpleNamespace(message=message, finish_reason=self.finish_reason)
        return SimpleNamespace(choices=[choice])


def answerer(stub, **kwargs):
    return AzureOpenAIAnswerer("https://x", "key", "gpt-4o", client=stub, **kwargs)


def http_error(cls, status):
    request = httpx.Request("POST", "https://x/openai/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


# ---- prompt building ------------------------------------------------------------


def test_message_numbers_every_source_and_ends_with_the_question():
    message, included = build_user_message(
        "Can staff use USB drives?", [passage(1), passage(2, "Backups run weekly.")], 5000
    )
    assert "[1] audit.docx (Document, page 1)" in message
    assert "[2] audit.docx" in message
    assert "Backups run weekly." in message
    assert message.rstrip().endswith("Question: Can staff use USB drives?")
    assert [p.number for p in included] == [1, 2]


def test_message_stops_before_the_budget_and_reports_what_fit():
    passages = [passage(n, "x" * 400) for n in range(1, 6)]
    message, included = build_user_message("q?", passages, 1000)
    assert 1 <= len(included) < 5
    assert all(f"[{p.number}]" in message for p in included)
    assert f"[{len(included) + 1}]" not in message


def test_first_source_is_always_kept_even_when_it_alone_exceeds_the_budget():
    message, included = build_user_message("q?", [passage(1, "y" * 5000)], 1000)
    assert [p.number for p in included] == [1]
    assert len(message) < 1300


# ---- parsing the reply ----------------------------------------------------------


def test_valid_reply_keeps_text_and_citations():
    reply = json.dumps({"answer": "USB drives are allowed [1].", "found": True, "citations": [1]})
    result = parse_answer(reply, {1, 2})
    assert (result.text, result.found, result.cited) == ("USB drives are allowed [1].", True, [1])


def test_citations_to_sources_that_do_not_exist_are_dropped():
    reply = json.dumps({"answer": "See [1] and [9].", "found": True, "citations": [1, 9, "x", 1]})
    assert parse_answer(reply, {1, 2}).cited == [1]


def test_citations_found_in_the_text_count_even_if_the_list_is_missing():
    reply = json.dumps({"answer": "Weekly [2].", "found": True})
    assert parse_answer(reply, {1, 2}).cited == [2]


def test_found_false_returns_no_citations():
    reply = json.dumps({"answer": "Nothing about holidays.", "found": False, "citations": [1]})
    result = parse_answer(reply, {1})
    assert (result.found, result.cited) == (False, [])
    assert result.text == "Nothing about holidays."


def test_found_false_without_text_uses_the_standard_message():
    result = parse_answer(json.dumps({"answer": "", "found": False}), {1})
    assert result.text == NOT_FOUND


def test_an_answer_with_no_valid_citation_is_not_shown_as_an_answer():
    reply = json.dumps({"answer": "Probably yes.", "found": True, "citations": []})
    result = parse_answer(reply, {1})
    assert (result.text, result.found, result.cited) == (NOT_FOUND, False, [])


def test_plain_text_reply_falls_back_to_bracket_numbers():
    result = parse_answer("Backups run weekly [2].", {1, 2})
    assert (result.found, result.cited) == (True, [2])


def test_empty_reply_is_an_error():
    with pytest.raises(QaError):
        parse_answer("   ", {1})
    with pytest.raises(QaError):
        parse_answer(None, {1})


# ---- the Azure answerer ---------------------------------------------------------


def test_azure_answerer_sends_a_grounded_json_request():
    reply = json.dumps({"answer": "Yes [1].", "found": True, "citations": [1]})
    stub = StubChat(reply)
    result = answerer(stub).answer("Can staff use USB drives?", [passage(1)])
    call = stub.calls[0]
    assert call["model"] == "gpt-4o"
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0]["role"] == "system"
    assert "ONLY the numbered sources" in call["messages"][0]["content"]
    assert "Can staff use USB drives?" in call["messages"][1]["content"]
    assert result.cited == [1]


def test_azure_answerer_cannot_cite_a_source_that_was_cut_for_length():
    reply = json.dumps({"answer": "From the last one [5].", "found": True, "citations": [5]})
    stub = StubChat(reply)
    passages = [passage(n, "z" * 400) for n in range(1, 6)]
    result = answerer(stub, max_context_chars=1000).answer("q?", passages)
    assert result.found is False


def test_azure_answerer_makes_no_call_without_sources():
    stub = StubChat("unused")
    result = answerer(stub).answer("anything?", [])
    assert (result.found, result.text) == (False, NOT_FOUND)
    assert stub.calls == []


def test_azure_errors_become_clear_messages():
    with pytest.raises(QaError, match="credentials"):
        answerer(StubChat(error=http_error(openai.AuthenticationError, 401))).answer("q", [passage(1)])
    with pytest.raises(QaError, match="rate limit"):
        answerer(StubChat(error=http_error(openai.RateLimitError, 429))).answer("q", [passage(1)])
    with pytest.raises(QaError, match="Answer service error"):
        answerer(StubChat(error=http_error(openai.InternalServerError, 500))).answer("q", [passage(1)])


def test_content_filter_is_reported():
    stub = StubChat("{}", finish_reason="content_filter")
    with pytest.raises(QaError, match="content filter"):
        answerer(stub).answer("q", [passage(1)])


# ---- the local stand-in ---------------------------------------------------------


def test_fake_answerer_quotes_the_top_source_and_cites_it():
    result = FakeAnswerer().answer("q?", [passage(1, "Backups run weekly."), passage(2)])
    assert result.found and result.cited == [1]
    assert "Backups run weekly." in result.text


def test_fake_answerer_with_no_sources_says_not_found():
    result = FakeAnswerer().answer("q?", [])
    assert (result.found, result.text) == (False, NOT_FOUND)
