
"""
A diagnostic script to check the status of all proxies from the database against stparts.ru.

This script iterates through all proxies marked as available in the database and makes a 
test request to stparts.ru through each one. It then categorizes each proxy as 'working', 
'blocked', or 'failed' based on the content of the HTML response.

It is used to determine if the parsing failures are due to stparts.ru blocking the
proxy pool. If a high percentage of proxies are blocked, it may be necessary to
acquire new proxies or switch to a different parsing method like Playwright.

Usage:
    python parser/scripts/check_proxies_for_stparts.py
"""
import asyncio

import sys
from pathlib import Path
import httpx
from tqdm.asyncio import tqdm

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


from loguru import logger

from parser.http import Proxy, get_proxies_from_db

# Configure Loguru for clear output
logger.remove()
logger.add(sys.stderr, level="INFO")

# --- Configuration ---
# URL to test against. A simple search query is a good choice.
TEST_URL = "https://stparts.ru/search"
TEST_PARAMS = {"pcode": "210202R920"}  # A common article code

# Concurrency limit to avoid overwhelming the server or getting banned.
CONCURRENCY_LIMIT = 20

# --- Success/Failure Markers ---
# Text expected in a successful response (i.e., a real search results page)
SUCCESS_MARKER = "searchResultsTable"
# Text expected in a response when the proxy is blocked
BLOCKED_MARKER = "Access Denied"


async def check_proxy(proxy: Proxy, stats: dict) -> None:
    """
    Checks a single proxy by making a request to the test URL.

    Args:
        proxy: The proxy to check.
        stats: A dictionary to update with the results (working/blocked).
    """
    proxy_id = "<proxy_info_unavailable>"
    try:
        proxy_id = f"{proxy['ip']}:{proxy['port']}"
        proxy_url = f"http://{proxy['username']}:{proxy['password']}@{proxy['ip']}:{proxy['port']}"

        async with httpx.AsyncClient(proxy=proxy_url, follow_redirects=True) as client:
            response = await client.get(TEST_URL, params=TEST_PARAMS, timeout=20.0)
            response.raise_for_status()
            html = response.text

            if BLOCKED_MARKER in html:
                stats["blocked"] += 1
            elif SUCCESS_MARKER in html:
                stats["working"] += 1
            else:
                stats["unknown"] += 1

    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        if stats["failed"] < 5:  # Log the first 5 network errors for diagnosis
            logger.error(f"[!] Proxy {proxy_id} failed with network error: {e.__class__.__name__}.")
        stats["failed"] += 1
    except Exception as e:
        if stats["failed"] < 5:  # Log the first 5 unexpected errors for diagnosis
            logger.exception(f"[!] An unexpected error occurred with proxy {proxy_id}: {e}")
        stats["failed"] += 1


async def main(limit: int = None):
    """
    Main function to fetch proxies and run the checks concurrently.
    """
    logger.info("--- Starting Proxy Check for stparts.ru ---")
    logger.info("Fetching proxies from the database...")

    proxies = await get_proxies_from_db()
    if not proxies:
        logger.error("No proxies found in the database. Exiting.")
        return

    total_proxies = len(proxies)
    logger.info(f"Found {total_proxies} proxies to check.")
    logger.info(f"Sample proxy record from DB: {proxies[0]}")

    if limit:
        proxies = proxies[:limit]
        logger.info(f"Limiting to {limit} proxies for this run.")

    stats = {"working": 0, "blocked": 0, "failed": 0, "unknown": 0}
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    tasks = []
    for proxy in proxies:

        async def task_wrapper(p: Proxy):
            async with semaphore:
                await check_proxy(p, stats)

        tasks.append(task_wrapper(proxy))

    await tqdm.gather(*tasks, desc="Checking Proxies")

    logger.info("--- Proxy Check Complete ---")
    logger.info("Summary:")
    logger.info(f"  Total Proxies Checked: {total_proxies}")
    logger.success(f"  Working Proxies: {stats['working']}")
    logger.warning(f"  Blocked Proxies: {stats['blocked']}")
    logger.error(f"  Failed Proxies (errors/timeouts): {stats['failed']}")
    if stats["unknown"] > 0:
        logger.error(f"  Unknown Responses: {stats['unknown']}")
    logger.info("----------------------------")

    if stats["working"] == 0:
        logger.critical("All checked proxies are blocked or failed. It is highly likely we need to switch to a different parsing approach like Playwright.")
    else:
        logger.info("Some proxies are still working. The existing setup can be used, but the proxy list may need cleaning.")


if __name__ == "__main__":
    asyncio.run(main(limit=10))
