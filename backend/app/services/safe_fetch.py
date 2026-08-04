"""SSRF-safe outbound fetcher for URLs that came from third-party feed content.

Everything else in this codebase talks to a fixed set of known hosts (Google News,
NewsAPI.org, NewsData.io, Mistral). Article enrichment is the first feature that fetches a
URL an outside party chose, which is a textbook SSRF surface: without these guards a
malicious or compromised feed entry could make the backend issue requests to the cloud
metadata endpoint, to Postgres, or to anything else reachable from inside the deployment's
network but not from the internet.

Guards, in the order they matter (see docs/google-news-quality-planning.html §14):

* https only — stricter than is_safe_article_url's http-or-https, which exists for
  rendering links, not for fetching them.
* Every hop's resolved IP is checked against private/loopback/link-local/reserved ranges,
  and redirects are followed manually so the check applies to each one rather than only to
  the URL we started with (a redirect to 169.254.169.254 otherwise walks straight past a
  first-hop-only check, and DNS rebinding does the same to a check that runs before connect).
* Bounded everywhere: connect/read timeout, redirect hops, response bytes.
* No credentials of any kind are ever attached.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("newsatlas.safe_fetch")

USER_AGENT = "NewsAtlas/1.0 (+https://github.com/mimiron01/NewsAtlas) article-enrichment"

MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 8.0


class UnsafeURLError(Exception):
    """The URL (or a host it redirected to) is not safe to fetch from this process."""


def _is_public_address(host: str) -> bool:
    """True only if every address `host` resolves to is a public unicast address.

    Every address, not just the first: a hostname with both a public and a private A record
    would otherwise pass the check and then be connected to at whichever address the
    resolver returned second.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def assert_safe_url(url: str) -> None:
    """Raises UnsafeURLError unless `url` is an https URL pointing at a public host."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeURLError(f"refusing to fetch non-https URL: {parsed.scheme or '(none)'}")
    if not parsed.hostname:
        raise UnsafeURLError("refusing to fetch URL with no host")
    if not _is_public_address(parsed.hostname):
        raise UnsafeURLError(f"refusing to fetch non-public host: {parsed.hostname}")


def fetch_text(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
) -> tuple[str, str]:
    """Fetches `url`, returning (final_url, body_text).

    Redirects are followed manually so assert_safe_url runs on every hop. Raises
    UnsafeURLError for a blocked target and httpx.HTTPError for a transport failure —
    callers treat both as "no enrichment for this article", never as fatal.
    """
    current_url = url
    with httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
        # Explicitly no cookie jar: nothing this fetcher touches should ever be able to
        # set state that a later fetch to a different host carries along.
        cookies=None,
    ) as client:
        for _ in range(max_redirects + 1):
            assert_safe_url(current_url)
            response = client.get(current_url)

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise UnsafeURLError("redirect without a Location header")
                current_url = str(response.url.join(location))
                continue

            response.raise_for_status()
            content = response.content[:max_bytes]
            encoding = response.encoding or "utf-8"
            return str(response.url), content.decode(encoding, errors="replace")

    raise UnsafeURLError(f"too many redirects (>{max_redirects})")


def resolve_final_url(
    url: str, *, timeout: float = DEFAULT_TIMEOUT, max_redirects: int = MAX_REDIRECTS
) -> str:
    """Follows redirects and returns the final URL without keeping the body.

    Used to turn a news.google.com/rss/articles/CBMi… redirect into the publisher URL
    behind it. Google's encoded payload can also be decoded offline, but that relies on an
    internal endpoint that has already changed once and will change again — following the
    redirect is slower and entirely robust to Google changing its encoding
    (docs/google-news-quality-planning.html §9.1).
    """
    current_url = url
    with httpx.Client(
        timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT}
    ) as client:
        for _ in range(max_redirects + 1):
            assert_safe_url(current_url)
            response = client.get(current_url)
            if not response.is_redirect:
                return str(response.url)
            location = response.headers.get("location")
            if not location:
                return current_url
            current_url = str(response.url.join(location))

    raise UnsafeURLError(f"too many redirects (>{max_redirects})")
