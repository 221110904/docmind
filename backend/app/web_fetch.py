"""Read a public web page or PDF into plain text.

The address comes from a user, so the server must not be tricked into opening things it
should not (this attack is called SSRF). The rules:

* only http and https, only the standard ports, no username or password in the address;
* every address the name resolves to must be a public one (no localhost, no private
  networks, no cloud metadata address), and the connection is made to the address that
  was checked, so the name cannot change between the check and the connection;
* every redirect is checked again, and there are at most three;
* the download is limited in size and in time.
"""

import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx


class FetchError(Exception):
    """The page could not be read. The message is safe to show to the user."""


MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_SECONDS = 20.0
MAX_PDF_PAGES = 80
ALLOWED_TYPES = {"text/html", "application/xhtml+xml", "text/plain", "application/pdf"}
USER_AGENT = "DocMindBot/1.0 (student project; reads public pages that a user asked for)"


@dataclass
class Page:
    url: str
    title: str
    # (page number, text). A web page is one segment numbered 1.
    segments: list[tuple[int, str]]
    truncated: bool = False


def _check_url(url: str):
    try:
        parts = urlsplit((url or "").strip())
        port = parts.port
    except ValueError:
        raise FetchError("That is not a valid web address.") from None
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https addresses can be read.")
    if not parts.hostname:
        raise FetchError("That is not a valid web address.")
    if parts.username or parts.password:
        raise FetchError("Addresses that contain a username or password are not allowed.")
    if port is not None and port not in (80, 443):
        raise FetchError("Only the standard web ports (80 and 443) are allowed.")
    return parts, port or (443 if parts.scheme == "https" else 80)


def _public_addresses(host: str, port: int, resolver) -> list[str]:
    try:
        infos = resolver(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise FetchError("That web address could not be found.") from None
    addresses: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise FetchError("That address points to a private or internal network, so it was not opened.")
        if str(ip) not in addresses:
            addresses.append(str(ip))
    if not addresses:
        raise FetchError("That web address could not be found.")
    return addresses


def fetch_page(
    url: str,
    *,
    max_chars: int = 24000,
    transport=None,
    resolver=socket.getaddrinfo,
) -> Page:
    """Download one page and return its text. Raises FetchError with a readable reason."""
    deadline = time.monotonic() + MAX_SECONDS
    current = url
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(10.0),
        follow_redirects=False,
        trust_env=False,  # never pick up proxy settings from the environment
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            parts, port = _check_url(current)
            ip = _public_addresses(parts.hostname, port, resolver)[0]
            host_in_url = f"[{ip}]" if ":" in ip else ip
            netloc = host_in_url + (f":{parts.port}" if parts.port else "")
            pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
            host_header = parts.hostname + (f":{parts.port}" if parts.port else "")
            headers = {
                "Host": host_header,
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.1",
                "Accept-Language": "en,ar;q=0.8",
            }
            extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
            try:
                with client.stream("GET", pinned, headers=headers, extensions=extensions) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("The site redirected without saying where.")
                        current = urljoin(current, location)
                        continue
                    return _read_response(response, current, deadline, max_chars)
            except httpx.TimeoutException:
                raise FetchError("The site took too long to answer.") from None
            except httpx.HTTPError:
                raise FetchError("The site could not be reached.") from None
        raise FetchError("The site redirected too many times.")


def _read_response(response, url: str, deadline: float, max_chars: int) -> Page:
    status = response.status_code
    if status in (401, 403, 429):
        raise FetchError(f"The site refused automated access (status {status}). Download the file and upload it instead.")
    if status >= 400:
        raise FetchError(f"The site answered with an error (status {status}).")
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        raise FetchError(f"That kind of file ({content_type or 'unknown'}) cannot be read. Use a web page or a PDF.")
    chunks, total = [], 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_BYTES:
            raise FetchError("The page is too large to read (over 5 MB).")
        if time.monotonic() > deadline:
            raise FetchError("The site took too long to send the page.")
        chunks.append(chunk)
    body = b"".join(chunks)

    if content_type == "application/pdf":
        return _pdf_page(body, url, max_chars)
    text, title = html_to_text(_decode(body, response.headers.get("content-type", "")), plain=content_type == "text/plain")
    if len(text) < 200:
        raise FetchError(
            "Very little text was found on that page. It may load its content with scripts, "
            "or need a login. Download the document and upload it instead."
        )
    truncated = len(text) > max_chars
    return Page(url, title or _name_from_url(url), [(1, text[:max_chars])], truncated)


def _decode(body: bytes, content_type_header: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type_header, re.I)
    if not match:
        match = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
        charset = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    else:
        charset = match.group(1)
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _name_from_url(url: str) -> str:
    parts = urlsplit(url)
    name = unquote(PurePosixPath(parts.path).name)
    return name or parts.hostname or url


def _pdf_page(body: bytes, url: str, max_chars: int) -> Page:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(body))
        if reader.is_encrypted:
            raise FetchError("The PDF is password protected.")
        segments, used, truncated = [], 0, False
        for number, page in enumerate(reader.pages, start=1):
            if number > MAX_PDF_PAGES:
                truncated = True
                break
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            room = max_chars - used
            if room <= 0:
                truncated = True
                break
            if len(text) > room:
                text, truncated = text[:room], True
            segments.append((number, text))
            used += len(text)
        title = ((reader.metadata.title if reader.metadata else None) or "").strip()
    except FetchError:
        raise
    except Exception:
        raise FetchError("The PDF could not be read.") from None
    if not segments:
        raise FetchError("The PDF has no readable text (it may be a scan). Upload it to DocMind instead.")
    return Page(url, title or _name_from_url(url), segments, truncated)


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "template", "iframe"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul", "ol", "main"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(raw: str, plain: bool = False) -> tuple[str, str]:
    """Return (readable text, page title) from an HTML or plain text page."""
    if plain:
        text, title = raw, ""
    else:
        extractor = _TextExtractor()
        extractor.feed(raw)
        text, title = "".join(extractor.parts), extractor.title
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, re.sub(r"\s+", " ", title).strip()
