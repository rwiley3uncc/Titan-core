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

OFFICIAL_ENTITY_DOMAINS = {
    "openai": ("openai.com",),
    "microsoft": ("microsoft.com", "support.microsoft.com"),
    "nvidia": ("nvidia.com",),
    "google": ("google.com", "deepmind.google"),
    "deepmind": ("deepmind.google", "google.com"),
    "python": ("python.org", "docs.python.org"),
    "fastapi": ("fastapi.tiangolo.com",),
}
HIGH_TRUST_PUBLIC_SUFFIXES = (".gov", ".edu")
REPUTABLE_REFERENCE_DOMAINS = (
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "britannica.com",
    "wikipedia.org",
)
WEAK_SOURCE_DOMAINS = (
    "reddit.com",
    "quora.com",
    "facebook.com",
    "tiktok.com",
    "pinterest.com",
)
CURRENT_FACT_KEYWORDS = ("current", "official", "announced", "leadership", "ceo", "board", "president")
MIN_SOURCE_SCORE = 55


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


def _normalize_domain(domain: str) -> str:
    normalized = (domain or "").strip().lower()
    return normalized[4:] if normalized.startswith("www.") else normalized


def _tokenize_query(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in (text or ""))
    return [part for part in cleaned.split() if part]


def _matches_domain(domain: str, candidate: str) -> bool:
    candidate = candidate.lower()
    return domain == candidate or domain.endswith(f".{candidate}")


def _query_entities(query: str) -> list[str]:
    lowered = (query or "").lower()
    return [entity for entity in OFFICIAL_ENTITY_DOMAINS if entity in lowered]


def _is_current_fact_query(query: str) -> bool:
    lowered = (query or "").lower()
    return any(keyword in lowered for keyword in CURRENT_FACT_KEYWORDS)


def score_source(source: VerifiedWebSource, query: str) -> int:
    score = 0
    domain = _normalize_domain(source.domain)
    title = source.title.lower()
    text = source.extracted_text.lower()
    query_lower = (query or "").lower()
    query_tokens = _tokenize_query(query)
    query_entities = _query_entities(query)
    is_secondary_source = any(_matches_domain(domain, reputable) for reputable in REPUTABLE_REFERENCE_DOMAINS)

    trust_class_score = 0
    matched_official_entity = False
    for entity in query_entities:
        if any(_matches_domain(domain, official_domain) for official_domain in OFFICIAL_ENTITY_DOMAINS[entity]):
            trust_class_score = max(trust_class_score, 60)
            matched_official_entity = True

    for suffix in HIGH_TRUST_PUBLIC_SUFFIXES:
        bare_suffix = suffix[1:]
        if domain == bare_suffix or domain.endswith(suffix):
            trust_class_score = max(trust_class_score, 40)

    if is_secondary_source:
        trust_class_score = max(trust_class_score, 25)

    for trusted in TRUSTED_DOMAINS:
        trusted = trusted.lower()
        if trusted.startswith("."):
            bare_suffix = trusted[1:]
            if domain == bare_suffix or domain.endswith(f".{bare_suffix}"):
                trust_class_score = max(trust_class_score, 40)
        elif _matches_domain(domain, trusted):
            trust_class_score = max(trust_class_score, 45 if not matched_official_entity else trust_class_score)

    score += trust_class_score

    if len(source.extracted_text) > 120:
        score += 10
    elif len(source.extracted_text) < 40:
        score -= 5 if matched_official_entity or trust_class_score >= 45 else 18
    elif len(source.extracted_text) < 80:
        score -= 3 if matched_official_entity or trust_class_score >= 45 else 8

    if query_entities and any(entity in title or entity in text for entity in query_entities):
        score += 10
    else:
        matching_tokens = sum(1 for token in query_tokens if len(token) > 2 and (token in title or token in text))
        score += min(matching_tokens * 4, 12)

    if _is_current_fact_query(query) and any(keyword in text or keyword in title for keyword in CURRENT_FACT_KEYWORDS):
        score += 8

    if any(_matches_domain(domain, bad_domain) for bad_domain in WEAK_SOURCE_DOMAINS):
        score -= 55

    if not matched_official_entity and trust_class_score == 0:
        score -= 15

    if trust_class_score < 45 and len(source.extracted_text) < 120:
        score -= 10

    score = max(0, min(score, 100))
    if is_secondary_source:
        score = min(score, 80)
    return score


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

        source.score = score_source(source, query)

        logger.info(
            "[verified_web] scored domain=%s score=%s url=%s",
            source.domain,
            source.score,
            source.url,
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
