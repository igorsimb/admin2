"""Manages HTTP sessions, proxy pools, and fetching logic."""

import asyncio
import random
from enum import Enum
from itertools import cycle
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlparse

import asyncpg
import httpx
from loguru import logger


class Proxy(TypedDict):
    """Represents the structure of a proxy server's data."""

    ip: str
    port: int
    username: str
    password: str
    proxy_type: str


class ProxyType(Enum):
    """
    Used in proxy_list table (proxy_type column).
    """
    DCV6_DEDICATED = "datacenter_ipv6_dedicated"
    DCV4_SHARED = "datacenter_ipv4_shared"
    DCV4_DEDICATED = "datacenter_ipv4_dedicated"
    MOBILE_DEDICATED = "mobile_dedicated"
    MOBILE_SHARED = "mobile_shared"
    RESIDENTIAL_SHARED = "residential_shared"
    RESIDENTIAL_DEDICATED = "residential_dedicated"

# --- DB Connection Details ---
DB_CONFIG = {
    "host": "185.175.47.222",
    "port": 5433,
    "user": "parse_user",
    "password": "password",
    "database": "parse",
}


async def get_proxies_from_db(proxy_type: ProxyType | None = None) -> list[Proxy]:
    """
    Fetches a list of available proxy servers from the external PostgreSQL database.

    Args:
        proxy_type: An optional filter to fetch only proxies of a specific type.
    """
    conn = None
    try:
        conn = await asyncpg.connect(**DB_CONFIG)

        query = "SELECT ip, port, username, password, proxy_type FROM proxy_list WHERE availability = TRUE"
        params = []

        if proxy_type:
            query += " AND proxy_type = $1"
            params.append(proxy_type.value)

        records = await conn.fetch(query, *params)

        logger.debug(f"Fetched {len(records)} proxies from the external database for type: {proxy_type or 'any'}.")
        # The records from asyncpg are list-like and dict-like.
        return [dict(record) for record in records]
    except (asyncpg.PostgresError, OSError) as e:  # OSError can happen on connection failure
        logger.exception(f"Failed to fetch proxies from external database: {e}. Returning an empty list.")
        return []
    finally:
        if conn:
            await conn.close()


class ProxySession:
    """
    Manages an individual httpx.AsyncClient, optionally configured to use a specific proxy.

    It includes retry logic for fetching HTML content.
    """

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Connection": "keep-alive",
        "Sec-Ch-Ua": '"Google Chrome";v="141", "Chromium";v="141", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    INITIAL_COOKIES = {"visited": "1", "visited_locale": "1"}

    def __init__(self, proxy: Proxy):
        self.proxy = proxy
        self.max_retries = 3
        self.base_delay_sec = 1.0
        self.max_delay_sec = 60.0

        proxy_url = f"http://{proxy['username']}:{proxy['password']}@{proxy['ip']}:{proxy['port']}"

        self.client = httpx.AsyncClient(
            http2=True,
            proxy=proxy_url,
            headers=self.BASE_HEADERS,
            cookies=self.INITIAL_COOKIES,
            timeout=httpx.Timeout(20.0, read=30.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Closes the underlying httpx.AsyncClient."""
        await self.client.aclose()

    async def fetch_html(self, url: str, params: dict[str, Any] | None = None) -> str:
        """
        Fetches HTML content from a URL with retry logic on failures.

        Retries on specific HTTP status codes {429, 503} with exponential
        backoff and jitter. Respects the 'Retry-After' header if present.
        """
        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                if e.response.status_code in {429, 503}:
                    delay = min(self.max_delay_sec, self.base_delay_sec * (2**attempt) + random.uniform(0, 1))
                    if e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                pass  # Ignore invalid header value
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries} failed for {url} with status {e.response.status_code}. "
                        f"Retrying in {delay:.2f} seconds."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Request to {url} failed with unrecoverable status {e.response.status_code}.")
                    raise
            except httpx.RequestError as e:
                logger.error(f"Request to {url} failed: {e}")
                if attempt < self.max_retries - 1:
                    delay = min(self.max_delay_sec, self.base_delay_sec * (2**attempt) + random.uniform(0, 1))
                    await asyncio.sleep(delay)
                else:
                    raise
        raise httpx.RequestError(f"All {self.max_retries} attempts to fetch {url} failed.")


class ProxyPool:
    """
    Manages a pool of ProxySession objects for making concurrent HTTP requests.
    """

    def __init__(self, proxies: list[Proxy]):
        self._proxies = proxies
        self._proxy_cycle = cycle(self._proxies)
        self._sessions: dict[str, ProxySession] = {}
        self.cooldown = set()  # To be implemented: logic for cooling down failing proxies

    @classmethod
    async def from_db(cls) -> "ProxyPool":
        """Creates a ProxyPool by loading available proxies from the database."""
        proxies = await get_proxies_from_db()
        return cls(proxies)

    def acquire(self) -> ProxySession | None:
        """
        Acquires a ProxySession from the pool using a round-robin strategy.
        Returns None if no proxies are available.
        """
        if not self._proxies:
            return None

        # Simple round-robin for now. Cooldown logic can be added here.
        next_proxy = next(self._proxy_cycle)
        proxy_key = f"{next_proxy['ip']}:{next_proxy['port']}"

        if proxy_key not in self._sessions:
            self._sessions[proxy_key] = ProxySession(next_proxy)

        return self._sessions[proxy_key]

    def release(self, session: ProxySession):
        """Releases a session back to the pool. Can be extended for cooldown."""
        # For now, this does nothing. In a more complex scenario, we could
        # mark the proxy for cooldown if it has been failing.
        pass

    async def close_all(self):
        """Closes all active ProxySession clients."""
        for session in self._sessions.values():
            await session.close()


def requested_article(url: str) -> str:
    """
    Extracts the article code from stparts.ru search URLs.

    Supports URLs of the format:
    - /search?pcode=<CODE>
    - /search/<brand>/<CODE>?disableFiltering
    """
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")

    if "search" in path_parts:
        if len(path_parts) > 2 and path_parts[0] == "search":
            # Format: /search/<brand>/<CODE>
            return path_parts[2]

        query_params = parse_qs(parsed_url.query)
        if "pcode" in query_params:
            # Format: /search?pcode=<CODE>
            return query_params["pcode"][0]

    raise ValueError(f"Could not extract article from URL: {url}")
