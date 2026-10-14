"""
Real web tools for the autonomous agent: search + fetch.
FREE MODE: DuckDuckGo HTML (no API key), plain httpx.
SSRF-safe fetch: http(s) only, public IPs only, size/time limits.
"""
import html
import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NEXUS-AI/1.0"
FETCH_TIMEOUT_SECONDS = 15
FETCH_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
SEARCH_MAX_RESULTS = 8


class ToolError(Exception):
    """Tool execution failure with a user-safe message."""


def _is_public_host(host: str) -> bool:
    """Resolve host and reject private/loopback/link-local/reserved addresses."""
    if not host:
        return False
    lowered = host.lower().strip(".")
    if lowered in ("localhost", "localhost.localdomain"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ToolError("Only http/https URLs are allowed")
    if not parsed.hostname:
        raise ToolError("URL has no hostname")
    if not _is_public_host(parsed.hostname):
        raise ToolError("URL resolves to a private/local address (blocked)")
    return url


def _decode_ddg_redirect(href: str) -> str:
    """DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<enc>."""
    if href.startswith("//"):
        href = "https:" + href
    try:
        qs = parse_qs(urlparse(href).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    except Exception:
        pass
    return href


def _strip_html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


async def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search the web via DuckDuckGo HTML (no API key). Returns real results."""
    query = (query or "").strip()
    if not query:
        raise ToolError("Empty search query")
    max_results = max(1, min(max_results, SEARCH_MAX_RESULTS))

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            resp = await client.post(
                "https://html.duckduckgo.com/html/", data={"q": query}
            )
        except httpx.HTTPError as e:
            raise ToolError(f"Search request failed: {e}") from e

    if resp.status_code != 200:
        raise ToolError(f"Search backend returned HTTP {resp.status_code}")

    body = resp.text
    # Result links: <a rel="nofollow" class="result__a" href="...">title</a>
    link_iter = re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippet_iter = re.finditer(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippets = [
        _strip_html_to_text(m.group(1)) for m in snippet_iter
    ]

    results: List[Dict[str, str]] = []
    for i, m in enumerate(link_iter):
        if len(results) >= max_results:
            break
        href = _decode_ddg_redirect(m.group(1).strip())
        title = _strip_html_to_text(m.group(2)).strip()
        if not href.startswith("http") or not title:
            continue
        snippet = snippets[i] if i < len(snippets) else ""
        results.append({"title": title, "url": href, "snippet": snippet[:400]})

    if not results:
        raise ToolError(f"No search results for '{query}' (or markup changed)")

    return {
        "query": query,
        "provider": "duckduckgo-html",
        "count": len(results),
        "results": results,
    }


async def fetch_url(url: str, max_chars: int = 12000) -> Dict[str, Any]:
    """Fetch a public URL and return readable text (HTML stripped)."""
    url = _validate_url((url or "").strip())

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise ToolError(f"HTTP {resp.status_code} fetching URL")
                ctype = resp.headers.get("content-type", "")
                if ctype and not any(
                    t in ctype for t in ("text/", "json", "xml", "html", "xhtml")
                ):
                    raise ToolError(f"Unsupported content-type: {ctype}")

                chunks: List[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > FETCH_MAX_BYTES:
                        raise ToolError(
                            f"Response exceeds size limit ({FETCH_MAX_BYTES // (1024*1024)} MB)"
                        )
                raw = b"".join(chunks)
        except httpx.HTTPError as e:
            raise ToolError(f"Fetch failed: {e}") from e

    charset = "utf-8"
    if "charset=" in ctype.lower():
        charset = ctype.lower().split("charset=")[-1].split(";")[0].strip() or "utf-8"
    try:
        text_body = raw.decode(charset, errors="replace")
    except LookupError:
        text_body = raw.decode("utf-8", errors="replace")

    if "html" in (ctype or "").lower() or text_body.lstrip()[:1] == "<":
        text = _strip_html_to_text(text_body)
    else:
        text = text_body

    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[truncated]"

    return {
        "url": url,
        "status": resp.status_code,
        "content_type": ctype,
        "chars": len(text),
        "text": text,
    }
