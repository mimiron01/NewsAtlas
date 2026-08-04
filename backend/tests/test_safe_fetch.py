"""SSRF guards for the one part of the app that fetches URLs chosen by third parties.

These are security tests, not behaviour tests: each one asserts that a specific class of
internal target stays unreachable from the enrichment fetcher.
"""
import httpx
import pytest

from app.services import safe_fetch
from app.services.safe_fetch import UnsafeURLError, assert_safe_url, fetch_text, resolve_final_url


def patch_resolution(monkeypatch, mapping: dict[str, list[str]]):
    """Stubs DNS so tests don't depend on the network or on real internal addresses."""

    def fake_getaddrinfo(host, _port):
        if host not in mapping:
            raise safe_fetch.socket.gaierror("unknown host")
        return [(None, None, None, None, (addr, 0)) for addr in mapping[host]]

    monkeypatch.setattr(safe_fetch.socket, "getaddrinfo", fake_getaddrinfo)


def test_rejects_non_https_scheme(monkeypatch):
    patch_resolution(monkeypatch, {"example.com": ["93.184.216.34"]})
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://example.com/a")


def test_rejects_file_and_gopher_schemes(monkeypatch):
    for url in ("file:///etc/passwd", "gopher://example.com/"):
        with pytest.raises(UnsafeURLError):
            assert_safe_url(url)


def test_rejects_loopback(monkeypatch):
    patch_resolution(monkeypatch, {"localhost.example": ["127.0.0.1"]})
    with pytest.raises(UnsafeURLError):
        assert_safe_url("https://localhost.example/")


def test_rejects_private_ranges(monkeypatch):
    patch_resolution(monkeypatch, {"internal.example": ["10.0.0.5"]})
    with pytest.raises(UnsafeURLError):
        assert_safe_url("https://internal.example/")


def test_rejects_cloud_metadata_link_local_address(monkeypatch):
    """169.254.169.254 is the canonical SSRF target on every major cloud."""
    patch_resolution(monkeypatch, {"metadata.example": ["169.254.169.254"]})
    with pytest.raises(UnsafeURLError):
        assert_safe_url("https://metadata.example/latest/meta-data/")


def test_rejects_a_host_that_resolves_to_both_public_and_private(monkeypatch):
    """Checking only the first address would let the second one through, since which
    address is connected to isn't ours to choose."""
    patch_resolution(monkeypatch, {"mixed.example": ["93.184.216.34", "10.1.2.3"]})
    with pytest.raises(UnsafeURLError):
        assert_safe_url("https://mixed.example/")


def test_rejects_unresolvable_host(monkeypatch):
    patch_resolution(monkeypatch, {})
    with pytest.raises(UnsafeURLError):
        assert_safe_url("https://nope.example/")


def test_accepts_a_public_host(monkeypatch):
    patch_resolution(monkeypatch, {"example.com": ["93.184.216.34"]})
    assert_safe_url("https://example.com/article")


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None, url=""):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.url = httpx.URL(url)
        self.encoding = "utf-8"

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


def patch_client(monkeypatch, responses: dict[str, FakeResponse]):
    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return responses[str(url)]

    monkeypatch.setattr(safe_fetch.httpx, "Client", FakeClient)


def test_redirect_to_a_private_host_is_blocked(monkeypatch):
    """The check has to run per hop: a public first hop redirecting inward is the whole
    point of the attack."""
    patch_resolution(
        monkeypatch, {"public.example": ["93.184.216.34"], "internal.example": ["10.0.0.5"]}
    )
    patch_client(
        monkeypatch,
        {
            "https://public.example/a": FakeResponse(
                status_code=302,
                headers={"location": "https://internal.example/secret"},
                url="https://public.example/a",
            )
        },
    )

    with pytest.raises(UnsafeURLError):
        fetch_text("https://public.example/a")


def test_follows_a_redirect_to_another_public_host(monkeypatch):
    patch_resolution(
        monkeypatch, {"public.example": ["93.184.216.34"], "other.example": ["93.184.216.35"]}
    )
    patch_client(
        monkeypatch,
        {
            "https://public.example/a": FakeResponse(
                status_code=302,
                headers={"location": "https://other.example/b"},
                url="https://public.example/a",
            ),
            "https://other.example/b": FakeResponse(
                content=b"<html>body</html>", url="https://other.example/b"
            ),
        },
    )

    final_url, body = fetch_text("https://public.example/a")

    assert final_url == "https://other.example/b"
    assert "body" in body


def test_response_body_is_truncated_to_the_cap(monkeypatch):
    patch_resolution(monkeypatch, {"public.example": ["93.184.216.34"]})
    patch_client(
        monkeypatch,
        {"https://public.example/a": FakeResponse(content=b"x" * 5000, url="https://public.example/a")},
    )

    _final, body = fetch_text("https://public.example/a", max_bytes=100)

    assert len(body) == 100


def test_redirect_loop_is_bounded(monkeypatch):
    patch_resolution(monkeypatch, {"loop.example": ["93.184.216.34"]})
    patch_client(
        monkeypatch,
        {
            "https://loop.example/a": FakeResponse(
                status_code=302,
                headers={"location": "https://loop.example/a"},
                url="https://loop.example/a",
            )
        },
    )

    with pytest.raises(UnsafeURLError):
        fetch_text("https://loop.example/a", max_redirects=3)


def test_resolve_final_url_returns_the_publisher_url(monkeypatch):
    patch_resolution(
        monkeypatch, {"news.google.com": ["93.184.216.34"], "publisher.example": ["93.184.216.35"]}
    )
    patch_client(
        monkeypatch,
        {
            "https://news.google.com/rss/articles/CBMi": FakeResponse(
                status_code=302,
                headers={"location": "https://publisher.example/story"},
                url="https://news.google.com/rss/articles/CBMi",
            ),
            "https://publisher.example/story": FakeResponse(url="https://publisher.example/story"),
        },
    )

    assert (
        resolve_final_url("https://news.google.com/rss/articles/CBMi")
        == "https://publisher.example/story"
    )
