from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from parser.http import ProxySession, requested_article


@pytest.mark.parametrize(
    "url, expected_article",
    [
        ("https://stparts.ru/search?pcode=0PN1113H52", "0PN1113H52"),
        ("https://stparts.ru/search/Hyundai-KIA/0PN1113H52?disableFiltering", "0PN1113H52"),
        ("/search/Hyundai-KIA/0PN1113H52?disableFiltering", "0PN1113H52"),
        ("/search?pcode=ABC-123", "ABC-123"),
    ],
)
def test_requested_article_success(url: str, expected_article: str) -> None:
    result = requested_article(url)
    assert result == expected_article


def test_requested_article_failure() -> None:
    invalid_url = "https://stparts.ru/products/some-product"
    with pytest.raises(ValueError, match="Could not extract article from URL"):
        requested_article(invalid_url)


@pytest.mark.asyncio
@patch("parser.http.httpx.AsyncClient", new_callable=MagicMock)  # constructor is sync → use MagicMock
async def test_fetch_html_simulated_429_triggers_backoff(MockAsyncClient: MagicMock) -> None:
    # Build a mock client instance whose async methods are AsyncMock
    mock_client = AsyncMock()
    MockAsyncClient.return_value = mock_client  # ProxySession will call httpx.AsyncClient(...)

    # Responses: first path raises HTTPStatusError (simulating 429), then succeeds
    response_429 = httpx.Response(
        429,
        request=httpx.Request("GET", "https://test.com"),
        headers={"Retry-After": "0.01"},
    )
    response_ok = httpx.Response(200, text="Success", request=httpx.Request("GET", "https://test.com"))

    mock_client.get.side_effect = [
        httpx.HTTPStatusError("Too Many Requests", request=response_429.request, response=response_429),
        response_ok,
    ]

    # Avoid real sleeping and assert backoff happened
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        dummy_proxy = {"ip": "127.0.0.1", "port": 8080, "username": "user", "password": "password"}
        session = ProxySession(proxy=dummy_proxy)

        result = await session.fetch_html("https://test.com")

        assert result == "Success"
        assert mock_client.get.await_count == 2
        mock_sleep.assert_awaited()  # or assert_awaited_once() if exactly once


@pytest.mark.asyncio
@patch("parser.http.httpx.AsyncClient", new_callable=MagicMock)
async def test_fetch_html_retry_delay_is_capped(MockAsyncClient: MagicMock) -> None:
    """Verify that the retry delay is capped by `max_delay_sec`."""
    mock_client = AsyncMock()
    MockAsyncClient.return_value = mock_client

    # Make it fail 3 times before succeeding
    response_503 = httpx.Response(503, request=httpx.Request("GET", "https://test.com"))
    response_ok = httpx.Response(200, text="Success", request=httpx.Request("GET", "https://test.com"))
    mock_client.get.side_effect = [
        httpx.HTTPStatusError("Service Unavailable", request=response_503.request, response=response_503),
        httpx.HTTPStatusError("Service Unavailable", request=response_503.request, response=response_503),
        httpx.HTTPStatusError("Service Unavailable", request=response_503.request, response=response_503),
        response_ok,
    ]

    # In http.py: max_retries = 3, base_delay_sec = 1.0, max_delay_sec = 60.0
    # The delays would be:
    # 1. 1*2^0 + jitter = ~1s
    # 2. 1*2^1 + jitter = ~2s
    # 3. 1*2^2 + jitter = ~4s
    # We will set max_delay_sec to 3 to test the cap

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        dummy_proxy = {"ip": "127.0.0.1", "port": 8080, "username": "user", "password": "password"}
        session = ProxySession(proxy=dummy_proxy)
        # Temporarily modify the constants on the instance for the test
        session.max_delay_sec = 3.0
        session.max_retries = 4  # Allow enough retries

        await session.fetch_html("https://test.com")

        assert mock_sleep.call_count == 3
        # Check that the delay was capped
        assert mock_sleep.call_args_list[0].args[0] <= 3.0  # 1s + jitter
        assert mock_sleep.call_args_list[1].args[0] <= 3.0  # 2s + jitter
        assert mock_sleep.call_args_list[2].args[0] <= 3.0  # 4s + jitter -> capped at 3
