from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import logging
from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from titan_core.config import get_search_provider, get_searxng_url, is_verified_web_enabled, settings


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
    source_status: str = "verified"
    confidence: str = "medium"


@dataclass
class VerifiedWebResult:
    query: str
    sources: list[VerifiedWebSource]
    source_status: str
    confidence: str


def fetch_trusted_page_text(url: str) -> str | None:
    # TODO: Implement lightweight trusted page retrieval for allowlisted
    # pages only. Keep it read-only, short-timeout, and fail closed.
    _ = url
    return None


def extract_readable_text(html: str) -> str:
    # TODO: Replace this placeholder with a minimal standard-library
    # extraction pass when full page retrieval is enabled.
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
            if domain.endswith(f".{suffix}") or domain == suffix:
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
        if not is_trusted_url(url):
            continue
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


def _brave_search_results(
    query: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict]:
    if not settings.search_api_key:
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
            "X-Subscription-Token": settings.search_api_key,
            "User-Agent": "TitanCore/verified-web",
        },
        method="GET",
    )
    opener = urlopen_fn or urlopen

    try:
        with opener(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        # Fail closed on provider errors. Titan should refuse rather than
        # guessing from model memory.
        logger.exception("[verified_web] provider=brave request_failed")
        return []

    results: list[dict] = []
    web_results = payload.get("web", {}).get("results", [])
    if not isinstance(web_results, list):
        logger.info("[verified_web] provider=brave returning no results reason=invalid_payload")
        return []

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
    request = Request(
        url=f"{base_url.rstrip('/')}/search?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "TitanCore/verified-web",
        },
        method="GET",
    )
    opener = urlopen_fn or urlopen

    try:
        with opener(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        # Fail closed on local provider errors rather than guessing.
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
        # Fail closed when no verified provider is configured.
        logger.info("[verified_web] returning no results reason=missing_provider")
        return []
    if provider == "brave":
        if not settings.search_api_key:
            logger.info("[verified_web] provider=brave returning no results reason=missing_api_key")
            return []
        return _brave_search_results(query)
    if provider == "searxng":
        return _searxng_search_results(query)
    logger.info("[verified_web] returning no results reason=unsupported_provider provider=%s", provider)
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
        # TODO: Prefer trusted retrieved page text over provider snippets
        # after fetch_trusted_page_text() is implemented.
        sources.append(
            VerifiedWebSource(
                title=title,
                url=url,
                domain=_result_domain(url),
                extracted_text=snippet,
                source_status=str(result.get("source_status") or "snippet_only"),
                confidence=str(result.get("confidence") or "medium"),
            )
        )

    if not sources:
        logger.info("[verified_web] returning None reason=no_usable_sources")
        return None

    logger.info("[verified_web] returning verified context sources=%s", len(sources))
    return VerifiedWebResult(
        query=query,
        sources=sources,
        source_status="snippet_only",
        confidence="medium",
    )
