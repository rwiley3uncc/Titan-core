from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from titan_core.config import settings


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


def _brave_search_results(
    query: str,
    urlopen_fn: Callable[..., object] | None = None,
) -> list[dict]:
    if not settings.search_api_key:
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
        return []

    results: list[dict] = []
    web_results = payload.get("web", {}).get("results", [])
    if not isinstance(web_results, list):
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
    return results


def _search_provider_results(query: str) -> list[dict]:
    provider = (settings.search_provider or "").strip().lower()
    if not provider or not settings.search_api_key:
        # Fail closed when no verified provider is configured.
        return []
    if provider == "brave":
        return _brave_search_results(query)
    return []


def build_verified_web_context(
    query: str,
    search_fn: Callable[[str], list[dict]] | None = None,
) -> VerifiedWebResult | None:
    if not settings.verified_web_enabled:
        return None

    fetch_results = search_fn or _search_provider_results
    trusted_results = filter_trusted_results(fetch_results(query))
    if not trusted_results:
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
        return None

    return VerifiedWebResult(
        query=query,
        sources=sources,
        source_status="snippet_only",
        confidence="medium",
    )
