import json
from io import BytesIO

import httpx
import pytest

from app.web_fetch import FetchError, fetch_page, html_to_text
from app.web_search import TavilySearch, WebSearchError

PUBLIC = lambda host, port, type=None: [(2, 1, 6, "", ("93.184.216.34", port))]
LONG = "<html><head><title>Policy</title></head><body><nav>menu</nav><p>" + ("Students must attend classes. " * 20) + "</p><script>x()</script></body></html>"


def resolver_for(ip):
    return lambda host, port, type=None: [(2, 1, 6, "", (ip, port))]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "http://user:pw@example.com/",
    "http://example.com:8080/", "not a url", "",
])
def test_bad_addresses_rejected(url):
    with pytest.raises(FetchError):
        fetch_page(url, resolver=PUBLIC, transport=httpx.MockTransport(lambda r: httpx.Response(200)))


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "172.16.0.1"])
def test_private_addresses_blocked(ip):
    called = []
    transport = httpx.MockTransport(lambda r: called.append(r) or httpx.Response(200))
    with pytest.raises(FetchError, match="private"):
        fetch_page("https://example.com/", resolver=resolver_for(ip), transport=transport)
    assert not called


def test_localhost_name_blocked():
    with pytest.raises(FetchError):
        fetch_page("http://localhost/")


def test_reads_html_and_pins_ip():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text=LONG, headers={"content-type": "text/html; charset=utf-8"})

    page = fetch_page("https://example.com/policy", resolver=PUBLIC, transport=httpx.MockTransport(handler))
    assert page.title == "Policy"
    assert "Students must attend" in page.segments[0][1]
    assert "menu" not in page.segments[0][1] and "x()" not in page.segments[0][1]
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.com"


def test_redirect_to_private_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    def resolver(host, port, type=None):
        ip = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
        return [(2, 1, 6, "", (ip, port))]

    with pytest.raises(FetchError, match="private"):
        fetch_page("https://example.com/", resolver=resolver, transport=httpx.MockTransport(handler))


def test_too_many_redirects():
    transport = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "https://example.com/again"}))
    with pytest.raises(FetchError, match="too many"):
        fetch_page("https://example.com/", resolver=PUBLIC, transport=transport)


def test_size_cap():
    big = b"a" * (5 * 1024 * 1024 + 10)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=big, headers={"content-type": "text/plain"}))
    with pytest.raises(FetchError, match="too large"):
        fetch_page("https://example.com/", resolver=PUBLIC, transport=transport)


def test_unsupported_type_and_blocked_site():
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x", headers={"content-type": "image/png"}))
    with pytest.raises(FetchError, match="cannot be read"):
        fetch_page("https://example.com/", resolver=PUBLIC, transport=t)
    t = httpx.MockTransport(lambda r: httpx.Response(403))
    with pytest.raises(FetchError, match="upload it instead"):
        fetch_page("https://example.com/", resolver=PUBLIC, transport=t)


def test_thin_page_rejected():
    t = httpx.MockTransport(lambda r: httpx.Response(200, text="<p>hi</p>", headers={"content-type": "text/html"}))
    with pytest.raises(FetchError, match="Very little text"):
        fetch_page("https://example.com/", resolver=PUBLIC, transport=t)


def test_pdf_pages_keep_numbers():
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 700, "First page about attendance")
    c.showPage()
    c.drawString(72, 700, "Second page about appeals")
    c.save()
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=buf.getvalue(), headers={"content-type": "application/pdf"}))
    page = fetch_page("https://example.com/p.pdf", resolver=PUBLIC, transport=t)
    assert [n for n, _ in page.segments] == [1, 2]
    assert "appeals" in page.segments[1][1]


def test_html_to_text_plain():
    text, title = html_to_text("<title> A  B </title><h1>Hi</h1><p>there</p>")
    assert title == "A B" and "Hi" in text and "there" in text


# ---- Tavily ----

def test_tavily_parses_results():
    def handler(request):
        assert request.headers["authorization"] == "Bearer k"
        assert json.loads(request.content)["query"] == "q"
        return httpx.Response(200, json={"results": [{"title": "T", "url": "https://a.edu/p", "content": "snip"}, {"url": ""}]})

    results = TavilySearch("k", transport=httpx.MockTransport(handler)).search("q")
    assert len(results) == 1 and results[0].domain == "a.edu" and results[0].snippet == "snip"


@pytest.mark.parametrize("status,msg", [(401, "API key"), (429, "limit"), (500, "error")])
def test_tavily_errors(status, msg):
    with pytest.raises(WebSearchError, match=msg):
        TavilySearch("k", transport=httpx.MockTransport(lambda r: httpx.Response(status))).search("q")


def test_tavily_bad_json():
    with pytest.raises(WebSearchError):
        TavilySearch("k", transport=httpx.MockTransport(lambda r: httpx.Response(200, text="no"))).search("q")
