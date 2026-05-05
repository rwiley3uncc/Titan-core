from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from titan_core.config import (
    get_brave_api_key,
    get_search_provider,
    is_verified_web_enabled,
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
    failure_reason: str | None = None


def score_source(source: VerifiedWebSource) -> int:
    score = 0
    domain = source.domain.lower()
    title = source.title.lower()
    text = source.extracted_text.lower()

    trusted_hit = False
    for trusted in TRUSTED_DOMAINS:
        trusted = trusted.lower()
        if trusted.startswith("."):
            suffix = trusted[1:]
            if domain == suffix or domain.endswith(f".{suffix}"):
                score += 45
                trusted_hit = True
        elif domain == trusted or domain.endswith(f".{trusted}"):
            score += 50
            trusted_hit = True

    if any(domain == suffix or domain.endswith(f".{suffix}") for suffix in ("edu", "gov")):
        score += 45
        trusted_hit = True

    if any(
        reputable in domain
        for reputable in ("wikipedia.org", "britannica.com", "reuters.com", "apnews.com", "bbc.com")
    ):
        score += 45
        trusted_hit = True

    if len(source.extracted_text) > 120:
        score += 10

    if any(keyword in text or keyword in title for keyword in ("official", "announced", "current", "leadership")):
        score += 10

    if any(bad in domain for bad in ["reddit", "quora", "tiktok", "facebook", "pinterest"]):
        score -= 45

    if domain.startswith("www."):
        domain = domain[4:]

    if not trusted_hit and len(source.extracted_text) < 80:
        score -= 10

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

        # Accept trusted domains
        if is_trusted_url(url):
            trusted.append(result)
            continue

        # ALSO allow Wikipedia + major knowledge sites
        domain = (urlparse(url).hostname or "").lower()

        if any(x in domain for x in ["wikipedia.org", "britannica.com"]):
            trusted.append(result)

    return trusted


def _result_domain(url: str) -> str:
    return (urlparse((url or "").strip()).hostname or "").lower()


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
    api_key = get_brave_api_key()
    logger.info("[verified_web] provider=brave")

    if not api_key:
        logger.info("[verified_web] provider=brave returning no results reason=missing_api_key")
        return []

    params = urlencode(
        {
            "q": query,
            "count": 10,
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


def _search_provider_results(query: str) -> list[dict]:
    provider = get_search_provider()

    if not provider:
        logger.info("[verified_web] returning no results reason=missing_provider")
        return []

    if provider == "brave":
        return _brave_search_results(query)

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

    logger.info(
        "[verified_web] build start env_enabled=%s provider=%s query=%s",
        env_enabled,
        provider or "<missing>",
        query,
    )

    if not env_enabled:
        logger.info("[verified_web] returning None reason=env_disabled")
        return None

    fetch_results = search_fn or _search_provider_results
    raw_results = fetch_results(query)

    logger.info("[verified_web] raw_results=%s", len(raw_results))

    if not raw_results:
        logger.info("[verified_web] returning None reason=no_raw_results")
        return None

    sources: list[VerifiedWebSource] = []
    candidate_count = 0

    for result in raw_results[:8]:
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

        candidate_count += 1
        source = VerifiedWebSource(
            title=title,
            url=url,
            domain=_result_domain(url),
            extracted_text=snippet,
            source_status=str(result.get("source_status") or "snippet_only"),
        )

        source.score = score_source(source)

        logger.info(
            "[verified_web] scored %s score=%s",
            source.domain,
            source.score,
        )

        if source.score >= MIN_SOURCE_SCORE:
            sources.append(source)

    logger.info("[verified_web] candidate_sources=%s", candidate_count)

    sources.sort(key=lambda item: item.score, reverse=True)

    if not sources:
        if candidate_count > 0:
            logger.info("[verified_web] returning diagnostic result reason=no_usable_sources_after_scoring")
            return VerifiedWebResult(
                query=query,
                sources=[],
                source_status="no_credible_sources",
                confidence="low",
                failure_reason="below_threshold",
            )
        logger.info("[verified_web] returning None reason=no_candidates")
        return None

    logger.info("[verified_web] usable_sources=%s", len(sources[:3]))

    return VerifiedWebResult(
        query=query,
        sources=sources[:3],
        source_status="snippet_only",
        confidence="medium",
        failure_reason=None,
    )
