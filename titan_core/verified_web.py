from __future__ import annotations

from dataclasses import dataclass
import gzip
import ipaddress
import json
import logging
from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from titan_core.config import (
    get_search_provider,
    get_searxng_url,
    is_verified_web_enabled,
    settings,
)

logger = logging.getLogger(__name__)

TRUSTED_DOMAINS = [
    ".edu",
    ".gov",
    "khanacademy.org",
    "openstax.org",
    "docs.python.org",
    "developer.mozilla.org",
    "support.microsoft.com",
    "openai.com",
    "fastapi.tiangolo.com",
    "python.org",
]


@dataclass
class VerifiedWebSource:
    title: str
    url: str
    domain: str
    extracted_text: str
    score: int = 0
    source_status: str = "verified"


@dataclass
class VerifiedWebResult:
    query: str
    sources: list[VerifiedWebSource]
    source_status: str
    confidence: str

MIN_SOURCE_SCORE = 70

def score_source(source: VerifiedWebSource) -> int:
    score = 0

    domain = source.domain.lower()
    text = source.extracted_text.lower()

    for trusted in TRUSTED_DOMAINS:
        if trusted in domain:
            score += 40

    if len(source.extracted_text) > 120:
        score += 10

    if "official" in text or "announced" in text:
        score += 10

    if any(bad in domain for bad in ["reddit", "quora", "tiktok", "facebook", "pinterest"]):
        score -= 40

    return max(0, min(score, 100))

def fetch_trusted_page_text(url: str) -> str | None:
    # TODO: Future full-page extraction.
    # Keep allowlist-only, read-only, short-timeout, and fail closed.
    _ = url
    return None


def extract_readable_text(html: str) -> str:
    # TODO: Future lightweight readable-text extraction.
    return html


def is_trusted_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())

    if parsed.scheme.lower() != "https":
        return False

    domain = (parsed.hostname or "").strip().lower()
    if not domain:
        return False

    for trusted in TRUSTED_DOMAINS:
        candidate = trusted.lower()

        if candidate.startswith("."):
            suffix = candidate[1:]
            if domain == suffix or domain.endswith(f".{suffix}"):
                return True
            continue

        if domain == candidate or domain.endswith(f".{candidate}"):
            return True

    return False


def filter_trusted_results(results: list[dict]) -> list[dict]:
    trusted: list[dict] = []

    for result in results:
        if not isinstance(result, dict):
            continue

        url = str(result.get("url") or "").strip()
        if is_trusted_url(url):
            trusted.append(result)

    return trusted


def _result_domain(url: str) -> str:
    return (urlparse((url or "").strip()).hostname or "").lower()


def is_allowed_searxng_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())

    if parsed.scheme.lower() not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    if host in {"localhost", "127.0.0.1", "::1"}:
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    return address.is_private or address.is_loopback


def _read_response_json(response: object) -> dict:
    raw = response.read()

    encoding = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            encoding = str(headers.get("Content-Encoding") or "").lower()
        except Exception:
            encoding = ""

    if encoding == "gzip":
        raw = gzip.decompress(raw)

    return json.loads(raw.decode("utf-8"))


def _brave_search_results(
    query: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict]:
    api_key = getattr(settings, "search_api_key", None)

    if not api_key:
        logger.info("[verified_web] provider=brave returning no results reason=missing_api_key")
        return []

    params = urlencode(
        {
            "q": query,
            "count": 5,
            "text_decorations": 0,
            "result_filter": "web",
        }
    )

    request = Request(
        url=f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
            "User-Agent": "TitanCore/verified-web",
        },
        method="GET",
    )

    opener = urlopen_fn or urlopen

    try:
        with opener(request, timeout=5) as response:
            payload = _read_response_json(response)
    except Exception:
        logger.exception("[verified_web] provider=brave request_failed")
        return []

    web_results = payload.get("web", {}).get("results", [])
    if not isinstance(web_results, list):
        logger.info("[verified_web] provider=brave returning no results reason=invalid_payload")
        return []

    results: list[dict] = []
    for item in web_results:
        if not isinstance(item, dict):
            continue

        results.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("description") or item.get("snippet") or "").strip(),
                "source_status": "snippet_only",
                "confidence": "medium",
            }
        )

    logger.info("[verified_web] provider=brave raw_results=%s", len(results))
    return results


def _searxng_search_results(
    query: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict]:
    base_url = get_searxng_url()

    logger.info("[verified_web] provider=searxng url=%s", base_url or "<missing>")

    if not is_allowed_searxng_url(base_url):
        logger.info("[verified_web] provider=searxng returning no results reason=disallowed_url")
        return []

    params = urlencode({"q": query, "format": "json"})
    search_url = f"{base_url.rstrip('/')}/search?{params}"

    request = Request(
        url=search_url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
        },
        method="GET",
    )

    opener = urlopen_fn or urlopen

    try:
        with opener(request, timeout=5) as response:
            payload = _read_response_json(response)
    except Exception:
        logger.exception("[verified_web] provider=searxng request_failed")
        return []

    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        logger.info("[verified_web] provider=searxng returning no results reason=invalid_payload")
        return []

    results: list[dict] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue

        results.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("content") or item.get("snippet") or "").strip(),
                "source_status": "snippet_only",
                "confidence": "medium",
            }
        )

    logger.info("[verified_web] provider=searxng raw_results=%s", len(results))
    return results


def _search_provider_results(query: str) -> list[dict]:
    provider = get_search_provider()

    if not provider:
        logger.info("[verified_web] returning no results reason=missing_provider")
        return []

    if provider == "brave":
        return _brave_search_results(query)

    if provider == "searxng":
        return _searxng_search_results(query)

    logger.info(
        "[verified_web] returning no results reason=unsupported_provider provider=%s",
        provider,
    )
    return []


def build_verified_web_context(
    query: str,
    search_fn: Callable[[str], list[dict]] | None = None,
) -> VerifiedWebResult | None:
    env_enabled = is_verified_web_enabled()
    provider = get_search_provider()
    searxng_url = get_searxng_url()

    logger.info(
        "[verified_web] build start env_enabled=%s provider=%s searxng_url=%s query=%s",
        env_enabled,
        provider or "<missing>",
        searxng_url or "<missing>",
        query,
    )

    if not env_enabled:
        logger.info("[verified_web] returning None reason=env_disabled")
        return None

    fetch_results = search_fn or _search_provider_results
    raw_results = fetch_results(query)

    trusted_results = filter_trusted_results(raw_results)

    logger.info(
        "[verified_web] provider=%s raw_results=%s trusted_results=%s",
        provider or "<missing>",
        len(raw_results),
        len(trusted_results),
    )

    if not trusted_results:
        logger.info("[verified_web] returning None reason=no_trusted_results")
        return None

    sources: list[VerifiedWebSource] = []

    for result in trusted_results[:3]:
        title = str(result.get("title") or "Verified source").strip()
        url = str(result.get("url") or "").strip()
        snippet = str(
            result.get("extracted_text")
            or result.get("snippet")
            or result.get("text")
            or ""
        ).strip()

        if not url or not snippet:
            continue

    source = VerifiedWebSource(
        title=title,
        url=url,
        domain=_result_domain(url),
        extracted_text=snippet,
        source_status=result.get("source_status", "")
    )

    source.score = score_source(source)

    if source.score >= MIN_SOURCE_SCORE:
        sources.append(source)

    if not sources:
        logger.info("[verified_web] returning None reason=no_usable_sources")
        return None

    logger.info("[verified_web] returning verified context sources=%s", len(sources))

    return VerifiedWebResult(
        query=query,
        sources=sources,
        source_status="snippet_only",
        confidence="medium",
    )from __future__ import annotations

from dataclasses import dataclass
import gzip
import ipaddress
import json
import logging
from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from titan_core.config import (
    get_search_provider,
    get_searxng_url,
    is_verified_web_enabled,
    settings,
)

logger = logging.getLogger(__name__)

TRUSTED_DOMAINS = [
    ".edu",
    ".gov",
    "khanacademy.org",
    "openstax.org",
    "docs.python.org",
    "developer.mozilla.org",
    "support.microsoft.com",
    "openai.com",
    "fastapi.tiangolo.com",
    "python.org",
    "microsoft.com",
    "reuters.com",
    "apnews.com",
    "bbc.com",
]

MIN_SOURCE_SCORE = 40


@dataclass
class VerifiedWebSource:
    title: str
    url: str
    domain: str
    extracted_text: str
    score: int = 0
    source_status: str = "verified"


@dataclass
class VerifiedWebResult:
    query: str
    sources: list[VerifiedWebSource]
    source_status: str
    confidence: str


def score_source(source: VerifiedWebSource) -> int:
    score = 0
    domain = source.domain.lower()
    text = source.extracted_text.lower()

    for trusted in TRUSTED_DOMAINS:
        trusted = trusted.lower()
        if trusted.startswith("."):
            suffix = trusted[1:]
            if domain == suffix or domain.endswith(f".{suffix}"):
                score += 40
        elif domain == trusted or domain.endswith(f".{trusted}"):
            score += 40

    if len(source.extracted_text) > 120:
        score += 10

    if "official" in text or "announced" in text or "current" in text:
        score += 10

    if any(bad in domain for bad in ["reddit", "quora", "tiktok", "facebook", "pinterest"]):
        score -= 40

    return max(0, min(score, 100))


def fetch_trusted_page_text(url: str) -> str | None:
    _ = url
    return None


def extract_readable_text(html: str) -> str:
    return html


def is_trusted_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())

    if parsed.scheme.lower() != "https":
        return False

    domain = (parsed.hostname or "").strip().lower()
    if not domain:
        return False

    for trusted in TRUSTED_DOMAINS:
        candidate = trusted.lower()

        if candidate.startswith("."):
            suffix = candidate[1:]
            if domain == suffix or domain.endswith(f".{suffix}"):
                return True
        else:
            if domain == candidate or domain.endswith(f".{candidate}"):
                return True

    return False


def filter_trusted_results(results: list[dict]) -> list[dict]:
    trusted: list[dict] = []

    for result in results:
        if not isinstance(result, dict):
            continue

        url = str(result.get("url") or "").strip()
        if is_trusted_url(url):
            trusted.append(result)

    return trusted


def _result_domain(url: str) -> str:
    return (urlparse((url or "").strip()).hostname or "").lower()


def is_allowed_searxng_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())

    if parsed.scheme.lower() not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    if host in {"localhost", "127.0.0.1", "::1"}:
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    return address.is_private or address.is_loopback


def _read_response_json(response: object) -> dict:
    raw = response.read()

    encoding = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            encoding = str(headers.get("Content-Encoding") or "").lower()
        except Exception:
            encoding = ""

    if encoding == "gzip":
        raw = gzip.decompress(raw)

    return json.loads(raw.decode("utf-8"))


def _brave_search_results(
    query: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict]:
    api_key = getattr(settings, "search_api_key", None)

    if not api_key:
        logger.info("[verified_web] provider=brave returning no results reason=missing_api_key")
        return []

    params = urlencode(
        {
            "q": query,
            "count": 5,
            "text_decorations": 0,
            "result_filter": "web",
        }
    )

    request = Request(
        url=f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
            "User-Agent": "TitanCore/verified-web",
        },
        method="GET",
    )

    opener = urlopen_fn or urlopen

    try:
        with opener(request, timeout=5) as response:
            payload = _read_response_json(response)
    except Exception:
        logger.exception("[verified_web] provider=brave request_failed")
        return []

    web_results = payload.get("web", {}).get("results", [])
    if not isinstance(web_results, list):
        logger.info("[verified_web] provider=brave returning no results reason=invalid_payload")
        return []

    results: list[dict] = []
    for item in web_results:
        if not isinstance(item, dict):
            continue

        results.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("description") or item.get("snippet") or "").strip(),
                "source_status": "snippet_only",
                "confidence": "medium",
            }
        )

    logger.info("[verified_web] provider=brave raw_results=%s", len(results))
    return results


def _searxng_search_results(
    query: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict]:
    base_url = get_searxng_url()

    logger.info("[verified_web] provider=searxng url=%s", base_url or "<missing>")

    if not is_allowed_searxng_url(base_url):
        logger.info("[verified_web] provider=searxng returning no results reason=disallowed_url")
        return []

    params = urlencode({"q": query, "format": "json"})
    search_url = f"{base_url.rstrip('/')}/search?{params}"

    request = Request(
        url=search_url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
        },
        method="GET",
    )

    opener = urlopen_fn or urlopen

    try:
        with opener(request, timeout=5) as response:
            payload = _read_response_json(response)
    except Exception:
        logger.exception("[verified_web] provider=searxng request_failed")
        return []

    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        logger.info("[verified_web] provider=searxng returning no results reason=invalid_payload")
        return []

    results: list[dict] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue

        results.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "snippet": str(item.get("content") or item.get("snippet") or "").strip(),
                "source_status": "snippet_only",
                "confidence": "medium",
            }
        )

    logger.info("[verified_web] provider=searxng raw_results=%s", len(results))
    return results


def _search_provider_results(query: str) -> list[dict]:
    provider = get_search_provider()

    if not provider:
        logger.info("[verified_web] returning no results reason=missing_provider")
        return []

    if provider == "brave":
        return _brave_search_results(query)

    if provider == "searxng":
        return _searxng_search_results(query)

    logger.info(
        "[verified_web] returning no results reason=unsupported_provider provider=%s",
        provider,
    )
    return []


def build_verified_web_context(
    query: str,
    search_fn: Callable[[str], list[dict]] | None = None,
) -> VerifiedWebResult | None:
    env_enabled = is_verified_web_enabled()
    provider = get_search_provider()
    searxng_url = get_searxng_url()

    logger.info(
        "[verified_web] build start env_enabled=%s provider=%s searxng_url=%s query=%s",
        env_enabled,
        provider or "<missing>",
        searxng_url or "<missing>",
        query,
    )

    if not env_enabled:
        logger.info("[verified_web] returning None reason=env_disabled")
        return None

    fetch_results = search_fn or _search_provider_results
    raw_results = fetch_results(query)
    trusted_results = filter_trusted_results(raw_results)

    logger.info(
        "[verified_web] provider=%s raw_results=%s trusted_results=%s",
        provider or "<missing>",
        len(raw_results),
        len(trusted_results),
    )

    if not trusted_results:
        logger.info("[verified_web] returning None reason=no_trusted_results")
        return None

    sources: list[VerifiedWebSource] = []

    for result in trusted_results[:5]:
        title = str(result.get("title") or "Verified source").strip()
        url = str(result.get("url") or "").strip()
        snippet = str(
            result.get("extracted_text")
            or result.get("snippet")
            or result.get("text")
            or ""
        ).strip()

        if not url or not snippet:
            continue

        source = VerifiedWebSource(
            title=title,
            url=url,
            domain=_result_domain(url),
            extracted_text=snippet,
            source_status=str(result.get("source_status") or "snippet_only"),
        )

        source.score = score_source(source)

        logger.info(
            "[verified_web] scored source domain=%s score=%s title=%s",
            source.domain,
            source.score,
            source.title,
        )

        if source.score >= MIN_SOURCE_SCORE:
            sources.append(source)

    sources.sort(key=lambda item: item.score, reverse=True)

    if not sources:
        logger.info("[verified_web] returning None reason=no_usable_sources_after_scoring")
        return None

    logger.info("[verified_web] returning verified context sources=%s", len(sources))

    return VerifiedWebResult(
        query=query,
        sources=sources[:3],
        source_status="snippet_only",
        confidence="medium",
    )