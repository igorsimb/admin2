"""
A simple script to perform a direct connectivity test to stparts.ru without a proxy.

This script serves as a control experiment. It makes a single request to a test URL
on stparts.ru using the application's standard browser headers but no proxy. 
It checks if the response is a valid results page or a block page and saves the 
full HTML response to a local file (`direct_response.html`) for inspection.

This is useful for verifying baseline connectivity and confirming what a successful, 
unblocked HTML response should look like.

Usage:
    python parser/scripts/check_stparts_direct.py
"""
import asyncio

import sys
from pathlib import Path
import httpx

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from parser.http import ProxySession

# Configure Loguru for clear output
logger.remove()
logger.add(sys.stderr, level="INFO")

# --- Configuration ---
TEST_URL = "https://stparts.ru/search"
TEST_PARAMS = {"pcode": "210202R920"}  # A common article code

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = ""

# --- Success/Failure Markers ---
SUCCESS_MARKER = "searchResultsTable"
BLOCKED_MARKER = "Access Denied"


async def main():
    """
    Main function to make a direct request to stparts.ru without a proxy.
    """
    logger.info("--- Starting Direct Check for stparts.ru ---")
    logger.info(f"Requesting URL: {TEST_URL} with params: {TEST_PARAMS}")

    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=ProxySession.BASE_HEADERS) as client:
            response = await client.get(TEST_URL, params=TEST_PARAMS, timeout=30.0)

        logger.info(f"Request completed with status code: {response.status_code}")

        html = response.text

        if BLOCKED_MARKER in html:
            logger.error("Result: The direct request was BLOCKED.")
            OUTPUT_FILE = SCRIPT_DIR / "direct_response_blocked.html"
        elif SUCCESS_MARKER in html:
            logger.success("Result: The direct request was SUCCESSFUL.")
            OUTPUT_FILE = SCRIPT_DIR / "direct_response_success.html"
        else:
            logger.warning("Result: The response did not contain a clear success or blocked marker.")

        # Save the response for inspection
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Full HTML response saved to: {OUTPUT_FILE}")

    except httpx.RequestError as e:
        logger.exception(f"A network error occurred during the direct request: {e}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    asyncio.run(main())
