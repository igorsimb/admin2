"""
Minimal Playwright probe that uses your get_proxies_from_db() to pick a proxy,
launch Chromium through that proxy, visit the test URL, detect gate vs success,
and persist storage_state per proxy for reuse.

Adjust TEST_URL, SUCCESS_MARKER and BLOCKED_MARKER as needed.
"""
import random
from pathlib import Path
import asyncio
import json
import time
import sys

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# import your proxy helper the same way as your other script
from parser.http import get_proxies_from_db, ProxyType  # type: ignore

# --- Configuration ---
TEST_URL = "https://stparts.ru/search?pcode=210202R920"
SUCCESS_MARKER = "searchResultsTable"    # found in good page HTML
BLOCKED_MARKERS = ("Access Denied", "Доступ запрещен") # found in the edge block page
AUTOCHECK_SNIPPET = "autocheck.dyn"      # the autocheck/hcaptcha link snippet
HEADLESS = False                         # set True to run headless (no manual captcha solve)
TIMEOUT_MS = 60_000                      # page load timeout
WAIT_BEFORE_CLOSING_SEC = 3              # seconds to wait before closing browser, 0 to disable
STORAGE_DIR = Path("./parser/scripts/playwright_storage")
STORAGE_DIR.mkdir(exist_ok=True)

def format_proxy_for_playwright(proxy: dict) -> dict | None:
    """
    Given a proxy dict from your DB, return a Playwright proxy dict.
    Expects keys: ip, port, username, password (username/password optional).
    """
    if not proxy:
        return None
    server = f"http://{proxy['ip']}:{proxy['port']}"
    result = {"server": server}
    if proxy.get("username") and proxy.get("password"):
        result["username"] = proxy["username"]
        result["password"] = proxy["password"]
    return result

def storage_path_for_proxy(proxy: dict) -> Path:
    safe = f"{proxy['ip']}-{proxy['port']}"
    return STORAGE_DIR / f"storage_{safe}.json"

def probe_one_proxy(proxy: dict | None, use_proxy: bool = True) -> None:
    if use_proxy and proxy:
        logger.info(f"Probing proxy {proxy['ip']}:{proxy['port']} (Type: {proxy.get('proxy_type', 'Unknown')})")
        pw_proxy = format_proxy_for_playwright(proxy)
        storage_file = storage_path_for_proxy(proxy)
    else:
        logger.info("Probing with direct connection (no proxy).")
        pw_proxy = None
        storage_file = STORAGE_DIR / "storage_direct.json"

    with sync_playwright() as p:
        launch_args = {
            "headless": HEADLESS,
            "args": [
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        }
        # provide proxy at launch so TLS/connection goes through proxy
        if pw_proxy:
            launch_args["proxy"] = pw_proxy

        browser = p.firefox.launch(**launch_args)

        # If we have an existing storage_state, load it; otherwise create a fresh context.
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
        }

        if storage_file.exists():
            logger.info(f"Loading existing storage state from {storage_file}")
            context = browser.new_context(storage_state=str(storage_file), **context_args)
        else:
            context = browser.new_context(**context_args)

        page = context.new_page()

        try:
            logger.info("Navigating to test URL...")
            page.goto(TEST_URL, timeout=TIMEOUT_MS)
            html = page.content()
            # quick checks
            if any(marker in html for marker in BLOCKED_MARKERS):
                logger.warning("Page contains Access Denied marker (edge blocking).")
                if AUTOCHECK_SNIPPET in html:
                    logger.warning("autocheck/hCaptcha snippet detected.")
                # Save HTML for debugging
                debug_file = STORAGE_DIR / f"blocked_{proxy['ip']}_{proxy['port'] if proxy else 'direct'}.html"
                debug_file.write_text(html, encoding="utf-8")
                logger.info(f"Blocked HTML saved to {debug_file}")
            elif SUCCESS_MARKER in html:
                logger.info("Success marker found — page looks like a real search result.")
                # persist storage state so subsequent runs can reuse cookies
                context.storage_state(path=str(storage_file))
                logger.info(f"Saved storage_state to {storage_file}")
                # optionally extract something simple:
                title = page.title()
                logger.info(f"Page title: {title}")
            else:
                logger.info("Neither success nor access-denied marker found. Saving HTML for inspection.")
                debug_file = STORAGE_DIR / f"unknown_{proxy['ip']}_{proxy['port'] if proxy else 'direct'}.html"
                debug_file.write_text(html, encoding="utf-8")
                logger.info(f"Unknown HTML saved to {debug_file}")

        except PWTimeoutError:
            logger.error("Playwright navigation timed out.")
        except Exception as exc:
            logger.exception("Unexpected error during probe: %s", exc)
        finally:
            if WAIT_BEFORE_CLOSING_SEC > 0:
                logger.info(f"Waiting for {WAIT_BEFORE_CLOSING_SEC} seconds before closing...")
                time.sleep(WAIT_BEFORE_CLOSING_SEC)
            try:
                page.close()
            except Exception:
                pass
            context.close()
            browser.close()

def main(limit: int = 1, use_proxy: bool = True, proxy_type: ProxyType | None = None):
    if use_proxy:
        if proxy_type:
            logger.info(f"Fetching proxies of type: {proxy_type.value}")
            proxies = asyncio.run(get_proxies_from_db(proxy_type=proxy_type))
        else:
            logger.info("Fetching all available proxies (no specific type filter).")
            proxies = asyncio.run(get_proxies_from_db())

        if not proxies:
            logger.error(f"No proxies returned. Exiting.")
            return
        
        proxies_to_probe = proxies[:limit]
        if proxies_to_probe:
            logger.info(f"Probing a random proxy from the {'specified type' if proxy_type else 'entire pool'}.")
            for proxy in proxies_to_probe:
                logger.info(f"Probing proxy {proxy['ip']}:{proxy['port']} (Type: {proxy.get('proxy_type', 'Unknown')})")
                probe_one_proxy(proxy=proxy, use_proxy=True)
        else:
            logger.warning(f"No proxies available to probe from the {'specified type' if proxy_type else 'entire pool'}.")
    else:
        probe_one_proxy(proxy=None, use_proxy=False)

if __name__ == "__main__":
    # To test a direct connection, run: main(use_proxy=False)
    # To test all available proxies (including those with NULL proxy_type), run: main(limit=1, use_proxy=True)
    # To test a specific proxy type, run: main(limit=1, use_proxy=True, proxy_type=ProxyType.DCV4_DEDICATED)
    main(limit=5, use_proxy=True)
