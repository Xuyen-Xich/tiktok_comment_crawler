"""Command-line entrypoint for the TikTok social data collection framework."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Annotated

import typer
from urllib.parse import quote_plus

from browser.browser_manager import BrowserManager
from config.settings import AppSettings, load_settings
from crawler.tiktok_crawler import TikTokCrawler
from models.crawl_result import CrawlResult
from storage import export_comments
from storage.json_writer import read_json
from utils.logger import configure_logging
from utils.text import extract_video_id, safe_filename
from utils.time import utc_now_iso

cli = typer.Typer(
    help="TikTok social listening crawler for classroom marketing analytics.",
    no_args_is_help=True,
)

EXPORT_FORMATS = {"csv", "json", "xlsx", "parquet", "sqlite", "all"}


def _normalize_formats(values: list[str]) -> list[str]:
    """Validate CLI export format values."""

    formats = [value.lower() for value in values]
    invalid = [value for value in formats if value not in EXPORT_FORMATS]
    if invalid:
        raise typer.BadParameter(f"Unsupported format(s): {', '.join(invalid)}")
    return formats


def _settings_from_cli(
    *,
    headless: bool,
    profile_dir: Path,
    output_dir: Path,
    max_scrolls: int,
    log_level: str,
    emulation: str,
    captcha_timeout: int,
) -> AppSettings:
    return load_settings(
        headless=headless,
        profile_dir=profile_dir,
        output_dir=output_dir,
        max_scrolls=max_scrolls,
        log_level=log_level,
        emulation=emulation,
        captcha_timeout_seconds=captcha_timeout,
    )


def _read_urls_file(path: Path) -> list[str]:
    """Read TikTok video URLs from a newline-delimited file."""

    if not path.exists():
        raise FileNotFoundError(f"URLs file not found: {path}")

    urls: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        url = raw_line.strip()
        if not url or url.startswith("#"):
            continue
        urls.append(url)
    return urls


async def _wait_for_manual_login(page, timeout_seconds: int, logger) -> None:
    """Wait up to timeout_seconds for the user to authenticate on TikTok."""

    from browser.captcha_handler import CaptchaHandler

    captcha_handler = CaptchaHandler(timeout_seconds=timeout_seconds, logger=logger)
    deadline = time.monotonic() + timeout_seconds
    logger.info("waiting_for_manual_login", extra={"timeout_seconds": timeout_seconds})
    print(f"Please login manually in the opened browser. Waiting up to {timeout_seconds} seconds...")

    while time.monotonic() < deadline:
        if not await captcha_handler.is_login_prompt_visible(page):
            await asyncio.sleep(2)
            return
        await asyncio.sleep(3)

    logger.warning("manual_login_timeout", extra={"timeout_seconds": timeout_seconds})
    print(f"Login wait timed out after {timeout_seconds} seconds. Continuing anyway.")


@cli.command()
def crawl(
    url: Annotated[str, typer.Option("--url", help="TikTok video URL.")],
    max_comments: Annotated[int | None, typer.Option("--max-comments", help="Stop after this many comments.")] = 200,
    keyword: Annotated[str, typer.Option("--keyword", help="Optional campaign/search label.")] = "",
    formats: Annotated[list[str], typer.Option("--format", help="csv, json, xlsx, parquet, sqlite, or all.")] = ["all"],
    output_dir: Annotated[Path, typer.Option("--output-dir", help="Folder for exports.")] = Path("output"),
    profile_dir: Annotated[Path, typer.Option("--profile-dir", help="Persistent browser profile folder.")] = Path("profiles/default"),
    headless: Annotated[bool, typer.Option("--headless", help="Run browser headless. Visible mode is best for captcha.", is_flag=True)] = False,
    max_scrolls: Annotated[int, typer.Option("--max-scrolls", help="Maximum comment scrolling rounds.")] = 30,
    emulation: Annotated[str, typer.Option("--emulation", help="desktop or mobile.")] = "desktop",
    captcha_timeout: Annotated[int, typer.Option("--captcha-timeout", help="Seconds to wait for manual captcha solving.")] = 600,
    ask_for_login: Annotated[bool, typer.Option("--ask-for-login", help="Ask user interactively if login is needed.", is_flag=True)] = False,
    skip_login_detection: Annotated[bool, typer.Option("--skip-login-detection", help="Completely skip login detection and auto-close attempts.", is_flag=True)] = True,
    wait_login_seconds: Annotated[int, typer.Option("--wait-login-seconds", help="(Deprecated) Use --ask-for-login instead. Seconds to wait for manual login before crawling.")] = 0,
    keep_open: Annotated[bool, typer.Option("--keep-open", help="Keep the browser open after crawling.", is_flag=True)] = False,
    log_level: Annotated[str, typer.Option("--log-level", help="DEBUG, INFO, WARNING, ERROR.")] = "INFO",
) -> None:
    """Crawl comments from one TikTok video URL."""

    asyncio.run(
        _crawl_async(
            url=url,
            keyword=keyword,
            max_comments=max_comments,
            formats=_normalize_formats(formats),
            output_dir=output_dir,
            profile_dir=profile_dir,
            headless=headless,
            max_scrolls=max_scrolls,
            emulation=emulation,
            captcha_timeout=captcha_timeout,
            ask_for_login=ask_for_login,
            skip_login_detection=skip_login_detection,
            wait_login_seconds=wait_login_seconds,
            keep_open=keep_open,
            log_level=log_level,
        )
    )


async def _crawl_async(
    *,
    url: str,
    keyword: str,
    max_comments: int | None,
    formats: list[str],
    output_dir: Path,
    profile_dir: Path,
    headless: bool,
    max_scrolls: int,
    emulation: str,
    captcha_timeout: int,
    ask_for_login: bool,
    skip_login_detection: bool,
    wait_login_seconds: int,
    keep_open: bool,
    log_level: str,
) -> CrawlResult:
    logger = configure_logging(log_level)
    settings = _settings_from_cli(
        headless=headless,
        profile_dir=profile_dir,
        output_dir=output_dir,
        max_scrolls=max_scrolls,
        log_level=log_level,
        emulation=emulation,
        captcha_timeout=captcha_timeout,
    )
    result = CrawlResult()
    browser_manager = BrowserManager(settings, logger)
    await browser_manager.start()
    try:
        assert browser_manager.page is not None
        crawler = TikTokCrawler(browser_manager.page, settings, logger, ask_for_login=ask_for_login, skip_login_detection=skip_login_detection)
        # Open the target page first so the user can log in if required.
        await crawler.open_url(url)
        if wait_login_seconds and wait_login_seconds > 0:
            logger.info("waiting_for_manual_login", extra={"seconds": wait_login_seconds})
            print(f"Please authenticate in the opened browser. Waiting {wait_login_seconds} seconds before crawling...")
            await asyncio.sleep(wait_login_seconds)
        comments = await crawler.crawl_video(url, keyword=keyword, max_comments=max_comments)
        base_name = safe_filename(f"post_{extract_video_id(url) or 'comments'}")
        output_files = export_comments(comments, output_dir=output_dir, base_name=base_name, formats=formats, logger=logger)
        result.comments = comments
        result.finished_at = utc_now_iso()
        result.output_files = output_files
        logger.info("crawl_completed", extra={"rows": len(comments), "files": [str(path) for path in output_files]})
    finally:
        if not keep_open:
            await browser_manager.close()
        else:
            logger.info("keeping_browser_open")
            print("Browser will be kept open after crawling. Press Enter to close and exit.")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except KeyboardInterrupt:
                pass
            await browser_manager.close()
    return result


@cli.command()
def search(
    keyword: Annotated[str, typer.Option("--keyword", help="TikTok search keyword.")],
    top_n: Annotated[int, typer.Option("--top-n", help="Number of search videos to crawl.")] = 5,
    max_comments_per_video: Annotated[int | None, typer.Option("--max-comments-per-video")] = 100,
    formats: Annotated[list[str], typer.Option("--format", help="csv, json, xlsx, parquet, sqlite, or all.")] = ["all"],
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("output"),
    profile_dir: Annotated[Path, typer.Option("--profile-dir")] = Path("profiles/default"),
    headless: Annotated[bool, typer.Option("--headless", is_flag=True)] = False,
    max_scrolls: Annotated[int, typer.Option("--max-scrolls")] = 25,
    search_scrolls: Annotated[int, typer.Option("--search-scrolls")] = 8,
    emulation: Annotated[str, typer.Option("--emulation")] = "desktop",
    captcha_timeout: Annotated[int, typer.Option("--captcha-timeout")] = 600,
    ask_for_login: Annotated[bool, typer.Option("--ask-for-login", is_flag=True)] = False,
    skip_login_detection: Annotated[bool, typer.Option("--skip-login-detection", is_flag=True)] = True,
    wait_login_seconds: Annotated[int, typer.Option("--wait-login-seconds")] = 0,
    keep_open: Annotated[bool, typer.Option("--keep-open", is_flag=True)] = False,
    log_level: Annotated[str, typer.Option("--log-level")] = "INFO",
) -> None:
    """Search TikTok and crawl comments from collected video results."""

    asyncio.run(
        _search_async(
            keyword=keyword,
            top_n=top_n,
            max_comments_per_video=max_comments_per_video,
            formats=_normalize_formats(formats),
            output_dir=output_dir,
            profile_dir=profile_dir,
            headless=headless,
            max_scrolls=max_scrolls,
            search_scrolls=search_scrolls,
            emulation=emulation,
            captcha_timeout=captcha_timeout,
            ask_for_login=ask_for_login,
            skip_login_detection=skip_login_detection,
            wait_login_seconds=wait_login_seconds,
            keep_open=keep_open,
            log_level=log_level,
        )
    )


async def _search_async(
    *,
    keyword: str,
    top_n: int,
    max_comments_per_video: int | None,
    formats: list[str],
    output_dir: Path,
    profile_dir: Path,
    headless: bool,
    max_scrolls: int,
    search_scrolls: int,
    emulation: str,
    captcha_timeout: int,
    ask_for_login: bool,
    skip_login_detection: bool,
    wait_login_seconds: int,
    keep_open: bool,
    log_level: str,
) -> CrawlResult:
    logger = configure_logging(log_level)
    settings = _settings_from_cli(
        headless=headless,
        profile_dir=profile_dir,
        output_dir=output_dir,
        max_scrolls=max_scrolls,
        log_level=log_level,
        emulation=emulation,
        captcha_timeout=captcha_timeout,
    )
    result = CrawlResult()
    browser_manager = BrowserManager(settings, logger)
    await browser_manager.start()
    try:
        assert browser_manager.page is not None
        crawler = TikTokCrawler(browser_manager.page, settings, logger, ask_for_login=ask_for_login, skip_login_detection=skip_login_detection)
        # Open the search page first so the user can log in if required.
        await crawler.open_url(f"https://www.tiktok.com/search?q={quote_plus(keyword)}")
        if wait_login_seconds and wait_login_seconds > 0:
            logger.info("waiting_for_manual_login", extra={"seconds": wait_login_seconds})
            print(f"Please authenticate in the opened browser. Waiting {wait_login_seconds} seconds before crawling...")
            await asyncio.sleep(wait_login_seconds)
        comments = await crawler.crawl_search(
            keyword,
            top_n=top_n,
            max_comments_per_video=max_comments_per_video,
            search_scrolls=search_scrolls,
        )
        base_name = safe_filename(f"search_{keyword}")
        output_files = export_comments(comments, output_dir=output_dir, base_name=base_name, formats=formats, logger=logger)
        result.comments = comments
        result.finished_at = utc_now_iso()
        result.output_files = output_files
        logger.info("search_completed", extra={"rows": len(comments), "files": [str(path) for path in output_files]})
    finally:
        if not keep_open:
            await browser_manager.close()
        else:
            logger.info("keeping_browser_open")
            print("Browser will be kept open after crawling. Press Enter to close and exit.")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except KeyboardInterrupt:
                pass
            await browser_manager.close()
    return result


@cli.command()
def batch_crawl(
    urls_file: Annotated[Path, typer.Option("--urls-file", help="Text file with TikTok video URLs, one per line.")] = Path("data/urls.txt"),
    max_comments: Annotated[int | None, typer.Option("--max-comments", help="Stop after this many comments per video.")] = 200,
    formats: Annotated[list[str], typer.Option("--format", help="csv, json, xlsx, parquet, sqlite, or all.")] = ["all"],
    output_dir: Annotated[Path, typer.Option("--output-dir", help="Folder for exports.")] = Path("output"),
    profile_dir: Annotated[Path, typer.Option("--profile-dir", help="Persistent browser profile folder.")] = Path("profiles/default"),
    headless: Annotated[bool, typer.Option("--headless", help="Run browser headless. Visible mode is best for captcha.", is_flag=True)] = False,
    max_scrolls: Annotated[int, typer.Option("--max-scrolls", help="Maximum comment scrolling rounds per video.")] = 30,
    emulation: Annotated[str, typer.Option("--emulation", help="desktop or mobile.")] = "desktop",
    captcha_timeout: Annotated[int, typer.Option("--captcha-timeout", help="Seconds to wait for manual captcha solving.")] = 600,
    login_timeout: Annotated[int, typer.Option("--login-timeout", help="Seconds to wait for manual TikTok login before crawling.")] = 300,
    ask_for_login: Annotated[bool, typer.Option("--ask-for-login", help="Ask user interactively if login is needed.", is_flag=True)] = False,
    skip_login_detection: Annotated[bool, typer.Option("--skip-login-detection", help="Completely skip login detection and auto-close attempts.", is_flag=True)] = False,
    keep_open: Annotated[bool, typer.Option("--keep-open", help="Keep the browser open after crawling.", is_flag=True)] = False,
    log_level: Annotated[str, typer.Option("--log-level", help="DEBUG, INFO, WARNING, ERROR.")] = "INFO",
) -> None:
    """Crawl comments from a list of TikTok videos sequentially."""

    asyncio.run(
        _batch_crawl_async(
            urls_file=urls_file,
            max_comments=max_comments,
            formats=_normalize_formats(formats),
            output_dir=output_dir,
            profile_dir=profile_dir,
            headless=headless,
            max_scrolls=max_scrolls,
            emulation=emulation,
            captcha_timeout=captcha_timeout,
            login_timeout=login_timeout,
            ask_for_login=ask_for_login,
            skip_login_detection=skip_login_detection,
            keep_open=keep_open,
            log_level=log_level,
        )
    )


async def _batch_crawl_async(
    *,
    urls_file: Path,
    max_comments: int | None,
    formats: list[str],
    output_dir: Path,
    profile_dir: Path,
    headless: bool,
    max_scrolls: int,
    emulation: str,
    captcha_timeout: int,
    login_timeout: int,
    ask_for_login: bool,
    skip_login_detection: bool,
    keep_open: bool,
    log_level: str,
) -> CrawlResult:
    logger = configure_logging(log_level)
    settings = _settings_from_cli(
        headless=headless,
        profile_dir=profile_dir,
        output_dir=output_dir,
        max_scrolls=max_scrolls,
        log_level=log_level,
        emulation=emulation,
        captcha_timeout=captcha_timeout,
    )
    urls = _read_urls_file(urls_file)
    browser_manager = BrowserManager(settings, logger)
    await browser_manager.start()
    error_urls: list[str] = []
    try:
        assert browser_manager.page is not None
        crawler = TikTokCrawler(
            browser_manager.page,
            settings,
            logger,
            ask_for_login=ask_for_login,
            skip_login_detection=skip_login_detection,
        )
        await browser_manager.page.goto("https://www.tiktok.com/", wait_until="domcontentloaded")
        await browser_manager.page.locator("body").wait_for(timeout=settings.page_timeout_ms)
        await _wait_for_manual_login(browser_manager.page, login_timeout, logger)

        for url in urls:
            try:
                comments = await crawler.crawl_video(url, keyword="", max_comments=max_comments)
                base_name = safe_filename(f"post_{extract_video_id(url) or 'comments'}")
                output_files = export_comments(
                    comments,
                    output_dir=output_dir,
                    base_name=base_name,
                    formats=formats,
                    logger=logger,
                )
                logger.info(
                    "batch_url_completed",
                    extra={"url": url, "rows": len(comments), "files": [str(path) for path in output_files]},
                )
            except Exception as exc:
                logger.warning("batch_url_failed", extra={"url": url, "error": str(exc)})
                error_urls.append(url)
                continue
    finally:
        if not keep_open:
            await browser_manager.close()
        else:
            logger.info("keeping_browser_open")
            print("Browser will be kept open after crawling. Press Enter to close and exit.")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except KeyboardInterrupt:
                pass
            await browser_manager.close()

    if error_urls:
        output_dir.mkdir(parents=True, exist_ok=True)
        error_file = output_dir / "error_urls.txt"
        error_file.write_text("\n".join(error_urls), encoding="utf-8")
        logger.warning("batch_error_urls_written", extra={"path": str(error_file), "count": len(error_urls)})

    result = CrawlResult()
    result.finished_at = utc_now_iso()
    return result


@cli.command()
def export(
    input_json: Annotated[Path, typer.Option("--input-json", help="Existing JSON export to convert.")],
    formats: Annotated[list[str], typer.Option("--format", help="csv, xlsx, parquet, sqlite, or all.")] = ["parquet"],
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("output"),
    base_name: Annotated[str | None, typer.Option("--base-name")] = None,
    log_level: Annotated[str, typer.Option("--log-level")] = "INFO",
) -> None:
    """Convert a JSON comments export into another format."""

    logger = configure_logging(log_level)
    comments = read_json(input_json)
    name = safe_filename(base_name or input_json.stem)
    output_files = export_comments(
        comments,
        output_dir=output_dir,
        base_name=name,
        formats=_normalize_formats(formats),
        logger=logger,
    )
    logger.info("export_completed", extra={"rows": len(comments), "files": [str(path) for path in output_files]})


if __name__ == "__main__":
    cli()
