from mycel.tools.m_fetch import is_valid_fetch_url


def test_is_valid_fetch_url_accepts_http_and_https() -> None:
    assert is_valid_fetch_url("https://example.com") is True
    assert is_valid_fetch_url("http://example.com/path?q=1") is True


def test_is_valid_fetch_url_rejects_non_http_or_missing_host() -> None:
    assert is_valid_fetch_url("ftp://example.com") is False
    assert is_valid_fetch_url("https:///missing-host") is False
    assert is_valid_fetch_url("not-a-url") is False
