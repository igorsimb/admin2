"""Orchestrates the stparts.ru parsing pipeline: fetch -> parse -> shape."""

import asyncio
import itertools
from typing import Any

import httpx
from loguru import logger
from selectolax.parser import HTMLParser

from .http import ProxyPool, ProxySession
from .stparts import parse_stparts
from .types import OfferRow


class MockProgressReporter:
    """A mock reporter for testing purposes when a real Celery task is not available."""

    def report_percentage(self, *, step: str, progress: int) -> None:
        print(f"[PROGRESS] {step}: {progress}%")

    def report_step(self, **kwargs: Any) -> None:
        print(f"[STEP] {kwargs}")


def _find_show_all_href(html: str) -> str | None:
    """Finds the redirect link for 'show all options' in the page."""
    tree = HTMLParser(html)
    for a in tree.css("a[href]"):
        if "показать все варианты" in a.text(strip=True).lower():
            href = a.attributes.get("href")
            return href if href else None
    return None


async def _fetch_and_parse_article(article: str, session: ProxySession, include_analogs: bool) -> list[OfferRow]:
    """Fetches and parses a single article code, handling potential redirects and security checks."""
    base_url = "https://stparts.ru"
    initial_url = f"{base_url}/search"
    params = {"pcode": article}

    # Start with the initial URL
    parsable_url = str(httpx.URL(initial_url, params=params))
    html = await session.fetch_html(initial_url, params=params)

    redirect_href = _find_show_all_href(html)
    if redirect_href:
        redirect_url = redirect_href
        if redirect_url.startswith("/"):
            redirect_url = f"{base_url}{redirect_url}"

        # Update the URL to be parsed and fetch the new content
        parsable_url = redirect_url
        html = await session.fetch_html(redirect_url)
    # --- DEBUGGING START ---
    logger.info(f"--- FINAL HTML for article {article} to be parsed ---\n{html}\n--- END HTML - --")
    # --- DEBUGGING END ---


    tree = HTMLParser(html)
    return parse_stparts(tree, parsable_url, include_analogs)


async def run_stparts_pipeline(
    articles: list[str],
    include_analogs: bool,
    reporter: Any = None,
    concurrency_limit: int = 10,
) -> list[OfferRow]:
    """
    Runs the full fetch and parse pipeline for a list of article codes.
    """
    if reporter is None:
        reporter = MockProgressReporter()

    pool = await ProxyPool.from_db()
    semaphore = asyncio.Semaphore(concurrency_limit)
    all_offers: list[OfferRow] = []
    total_articles = len(articles)
    completed_count = 0
    lock = asyncio.Lock()

    reporter.report_step(step="FETCHING", status="IN_PROGRESS")

    async def task(article: str) -> None:
        nonlocal completed_count
        async with semaphore:
            session = pool.acquire()
            if session is None:
                async with lock:
                    completed_count += 1
                return

            try:
                offers = await _fetch_and_parse_article(article, session, include_analogs)
                all_offers.extend(offers)
            except Exception as e:
                logger.exception(f"Failed to process article {article}: {e}")
                reporter.report_step(step="FETCHING", status="FAILURE", details={"error": str(e), "article": article})
            finally:
                pool.release(session)
                async with lock:
                    completed_count += 1
                    progress_pct = int((completed_count / total_articles) * 100)
                    reporter.report_percentage(step="FETCHING", progress=progress_pct)

    await asyncio.gather(*[task(article) for article in articles])
    await pool.close_all()

    reporter.report_step(step="FILTERING", status="IN_PROGRESS")

    priced_offers = [offer for offer in all_offers if offer.price is not None]

    # Sort by article, then by price (asc), quantity (desc), and deadline (asc)
    priced_offers.sort(key=lambda o: (o.a, o.price, -(o.quantity or 0), o.delivery or 999))

    final_results: list[OfferRow] = []
    for _, group in itertools.groupby(priced_offers, key=lambda o: o.a):
        final_results.extend(list(group)[:10])

    reporter.report_step(step="FILTERING", status="SUCCESS")

    return final_results
