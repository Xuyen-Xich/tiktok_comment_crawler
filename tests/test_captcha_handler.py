import asyncio

from browser.captcha_handler import CaptchaHandler


class DummyLocator:
    def __init__(self, inner_text: str = "", visible: bool = False, count: int = 0) -> None:
        self._inner_text = inner_text
        self._visible = visible
        self._count = count
        self.first = self

    async def inner_text(self, timeout: int | None = None) -> str:
        return self._inner_text

    async def is_visible(self, timeout: int | None = None) -> bool:
        return self._visible

    async def count(self) -> int:
        return self._count

    def nth(self, index: int) -> "DummyLocator":
        return self


class FakeLoginPage:
    def __init__(self) -> None:
        self.call_count = 0

    def locator(self, selector: str) -> DummyLocator:
        if selector == "body":
            self.call_count += 1
            if self.call_count < 3:
                return DummyLocator(inner_text="Please log in to continue", visible=True)
            return DummyLocator(inner_text="Welcome back", visible=True)
        if selector == "div[role='dialog']":
            return DummyLocator(inner_text="Log in", visible=True, count=1)
        return DummyLocator()


async def test_login_prompt_detected_and_resolves() -> None:
    handler = CaptchaHandler(timeout_seconds=5, logger=__import__("logging").getLogger("test"))
    page = FakeLoginPage()

    assert await handler.is_login_prompt_visible(page)

    await handler.wait_for_login_if_needed(page)
    assert page.call_count >= 2


async def test_login_prompt_not_visible_for_normal_page() -> None:
    handler = CaptchaHandler(timeout_seconds=1, logger=__import__("logging").getLogger("test"))

    class NormalPage:
        def locator(self, selector: str) -> DummyLocator:
            if selector == "body":
                return DummyLocator(inner_text="Search results for skincare", visible=True)
            return DummyLocator()

    assert not await handler.is_login_prompt_visible(NormalPage())
