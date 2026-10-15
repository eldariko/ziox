"""Tests for LinkValidator and verified link resolution in Humanizer."""

import pytest
from unittest.mock import patch, MagicMock
from engine.link_validator import LinkValidator
from engine.humanizer import Humanizer


@pytest.fixture(autouse=True)
def clear_validator_cache():
    LinkValidator.clear_cache()
    yield
    LinkValidator.clear_cache()


def test_is_valid_url_syntax():
    assert LinkValidator.is_valid_url_syntax("https://www.un.org/unispal/") is True
    assert LinkValidator.is_valid_url_syntax("http://example.com/test") is True
    assert LinkValidator.is_valid_url_syntax("not-a-url") is False
    assert LinkValidator.is_valid_url_syntax("") is False
    assert LinkValidator.is_valid_url_syntax(None) is False


def test_link_validator_live_url():
    # Test against real live UN partition document
    url = "https://www.un.org/unispal/document/auto-insert-185393/"
    is_alive, status = LinkValidator.check_url(url, verify_content=True)
    assert is_alive is True
    assert status == 200
    assert LinkValidator.is_alive(url) is True


def test_link_validator_caching(monkeypatch):
    url = "https://mock-valid-source.org/test"

    call_count = 0

    def mock_urlopen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status = 200
        # Return substantive text body (>= 60 words)
        resp.read.return_value = b"<html><body>" + b" verified factual source article paragraph word" * 70 + b"</body></html>"
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    # First call: hits network
    is_ok, status = LinkValidator.check_url(url, use_cache=True, verify_content=True)
    assert is_ok is True
    assert call_count == 1

    # Second call: served from in-memory cache
    is_ok2, status2 = LinkValidator.check_url(url, use_cache=True, verify_content=True)
    assert is_ok2 is True
    assert call_count == 1  # No additional network hit!


def test_link_validator_dead_url(monkeypatch):
    dead_url = "https://dead-broken-source.gov/404"

    import urllib.error
    def mock_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError(dead_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    is_ok, status = LinkValidator.check_url(dead_url)
    assert is_ok is False
    assert status == 404
    assert LinkValidator.is_alive(dead_url) is False


def test_link_validator_rejects_empty_incapsula_stub(monkeypatch):
    stub_url = "https://stub-page.gov/challenge"

    def mock_urlopen(*args, **kwargs):
        resp = MagicMock()
        resp.status = 200
        # Typical Incapsula JS challenge stub with no actual text
        resp.read.return_value = (
            b"<html><head><script src=\"/_Incapsula_Resource?SWUDNSAI=31\"></script></head>"
            b"<body></body></html>"
        )
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    is_ok, status = LinkValidator.check_url(stub_url, verify_content=True)
    assert is_ok is False
    assert status == 200  # HTTP was 200, but rejected because body is an empty bot challenge


def test_humanizer_drops_dead_link_and_falls_back_to_whitelist(monkeypatch):
    """
    If a proposed link returns 404, Humanizer should check whitelist for matching keywords.
    """
    dead_link = "https://fake-aid-dashboard.org/broken-link-404"
    valid_whitelist = "https://govextra.gov.il/cogat/humanitarian-efforts/home/"

    def mock_check_url(url, **kwargs):
        if url == dead_link:
            return False, 404
        return True, 200

    monkeypatch.setattr(LinkValidator, "check_url", mock_check_url)

    text = "Over 30,000 aid trucks entered via Kerem Shalom crossing."
    sanitized = Humanizer.sanitize(text, link=dead_link, auto_attach_whitelist=True, validate_links=True)

    # Dead link must NOT be attached
    assert dead_link not in sanitized
    # Whitelisted link should be attached as fallback
    assert valid_whitelist in sanitized


def test_humanizer_omits_link_when_all_fail(monkeypatch):
    """
    If both proposed link and whitelist fail or are absent, post clean narrative without broken URL.
    """
    dead_link = "https://fake-link.org/404"

    monkeypatch.setattr(LinkValidator, "is_alive", lambda url, **kwargs: False)

    text = "General commentary regarding diplomatic negotiations."
    sanitized = Humanizer.sanitize(text, link=dead_link, auto_attach_whitelist=False, validate_links=True)

    assert dead_link not in sanitized
    assert "https://" not in sanitized
    assert "General commentary regarding diplomatic negotiations." in sanitized
