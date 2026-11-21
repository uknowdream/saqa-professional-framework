"""Unit tests for saqa.browser_smoke."""
from __future__ import annotations

from contextlib import contextmanager

from saqa import browser_smoke


class _FakeLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self) -> str:
        return self._text


class _FakePage:
    def __init__(self, title: str = "SAQA", body: str = "ready") -> None:
        self._title = title
        self._body = body
        self.content = ""

    def set_content(self, html: str) -> None:
        self.content = html

    def title(self) -> str:
        return self._title

    def locator(self, selector: str) -> _FakeLocator:
        assert selector == "body"
        return _FakeLocator(self._body)


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    def new_page(self) -> _FakePage:
        return self._page

    def close(self) -> None:
        self.closed = True


class _FakeBrowserType:
    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser
        self.launched_headless: bool | None = None

    def launch(self, *, headless: bool = True) -> _FakeBrowser:
        self.launched_headless = headless
        return self._browser


class _FakePlaywright:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.chromium = _FakeBrowserType(browser)
        self.firefox = _FakeBrowserType(browser)
        self.webkit = _FakeBrowserType(browser)


def test_browser_smoke_rejects_unsupported_browser(monkeypatch, capsys):
    monkeypatch.setenv("SAQA_BROWSER", "safari-invalid")
    assert browser_smoke.main() == 2
    assert "Unsupported SAQA_BROWSER" in capsys.readouterr().err


def test_browser_smoke_reports_missing_playwright(monkeypatch, capsys):
    monkeypatch.setenv("SAQA_BROWSER", "chromium")

    def _missing():
        raise RuntimeError("Playwright is not installed.")

    monkeypatch.setattr(browser_smoke, "_get_sync_playwright", _missing)
    assert browser_smoke.main() == 2
    assert "Playwright is not installed." in capsys.readouterr().err


def test_browser_smoke_passes_and_closes_browser(monkeypatch, capsys):
    monkeypatch.setenv("SAQA_BROWSER", "firefox")
    browser = _FakeBrowser(_FakePage(title="SAQA", body="ready"))

    @contextmanager
    def _fake_sync_playwright():
        yield _FakePlaywright(browser)

    monkeypatch.setattr(browser_smoke, "_get_sync_playwright", lambda: _fake_sync_playwright)
    assert browser_smoke.main() == 0
    assert browser.closed is True
    assert "firefox: PASS" in capsys.readouterr().out


def test_browser_smoke_fails_on_unexpected_page_content(monkeypatch):
    monkeypatch.setenv("SAQA_BROWSER", "webkit")
    browser = _FakeBrowser(_FakePage(title="WRONG", body="ready"))

    @contextmanager
    def _fake_sync_playwright():
        yield _FakePlaywright(browser)

    monkeypatch.setattr(browser_smoke, "_get_sync_playwright", lambda: _fake_sync_playwright)
    assert browser_smoke.main() == 1
    assert browser.closed is True
