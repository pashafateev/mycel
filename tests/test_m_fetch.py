import mycel.tools.m_fetch as m_fetch


class _FakeResponse:
    def __init__(self, body: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.content = body.encode("utf-8")
        self.encoding = "utf-8"
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, _url: str) -> _FakeResponse:
        return self._response


def test_is_valid_fetch_url_accepts_http_and_https() -> None:
    assert m_fetch.is_valid_fetch_url("https://example.com") is True
    assert m_fetch.is_valid_fetch_url("http://example.com/path?q=1") is True


def test_is_valid_fetch_url_rejects_non_http_or_missing_host() -> None:
    assert m_fetch.is_valid_fetch_url("ftp://example.com") is False
    assert m_fetch.is_valid_fetch_url("https:///missing-host") is False
    assert m_fetch.is_valid_fetch_url("not-a-url") is False


def test_fetch_url_summary_keeps_normal_page_behavior(monkeypatch) -> None:
    response = _FakeResponse("<html><body><h1>Hello</h1><p>World</p></body></html>")
    monkeypatch.setattr(m_fetch.httpx, "Client", lambda **_: _FakeClient(response))

    result = m_fetch.fetch_url_summary("https://example.com/path?x=1")

    assert result.startswith("source: https://example.com/path")
    assert "Hello" in result
    assert "World" in result


def test_fetch_url_summary_detects_js_required_page(monkeypatch) -> None:
    response = _FakeResponse("<html><body><noscript>JavaScript required</noscript></body></html>")
    monkeypatch.setattr(m_fetch.httpx, "Client", lambda **_: _FakeClient(response))

    result = m_fetch.fetch_url_summary("https://example.com/js")

    assert "Try a print/export/raw-content URL instead." in result


def test_fetch_url_summary_detects_app_shell_page(monkeypatch) -> None:
    response = _FakeResponse(
        "<html><head><script src='a.js'></script><script src='b.js'></script></head>"
        "<body><div id='root'></div></body></html>"
    )
    monkeypatch.setattr(m_fetch.httpx, "Client", lambda **_: _FakeClient(response))

    result = m_fetch.fetch_url_summary("https://example.com/app")

    assert "Try a print/export/raw-content URL instead." in result


def test_fetch_url_summary_avoids_dumping_css_payload(monkeypatch) -> None:
    response = _FakeResponse(
        "body{margin:0;color:#111}.app{display:flex;align-items:center}",
        content_type="text/css",
    )
    monkeypatch.setattr(m_fetch.httpx, "Client", lambda **_: _FakeClient(response))

    result = m_fetch.fetch_url_summary("https://example.com/styles.css")

    assert "Try a print/export/raw-content URL instead." in result
    assert "margin:0" not in result
