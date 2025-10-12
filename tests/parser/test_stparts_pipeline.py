from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from parser.stparts_pipeline import run_stparts_pipeline


class MockProgressReporter:
    def __init__(self):
        self.steps = []
        self.percentages = []

    def report_step(self, **kwargs):
        self.steps.append(kwargs)

    def report_percentage(self, *, step: str, progress: int):
        self.percentages.append((step, progress))


# HTML fixture with 15 offers for the same article to test top-10 logic
HTML_FOR_TOP_10_TEST = """
<table id="searchResultsTable">
    <tbody>
        {}
    </tbody>
</table>
""".format(
    "\n".join(
        f'''<tr class="resultTr2" data-brand="Brand" data-output-price="{i}.00" 
                   data-availability="10" data-deadline="24" data-is-analog="0">
               <td class="resultDescription">Item {i}</td>
               <td class="resultWarehouse">WH{i}</td>
            </tr>'''
        for i in range(1, 16)
    )
)

# HTML fixture for testing the redirect link
HTML_WITH_REDIRECT_LINK = """
<a href="/final-results-page">Показать все варианты</a>
"""

HTML_FINAL_RESULTS = """
<table id="searchResultsTable">
    <tbody>
        <tr class="resultTr2" data-brand="Brand" data-output-price="99.00" 
            data-availability="10" data-deadline="24" data-is-analog="0">
            <td class="resultDescription">Final Item</td>
            <td class="resultWarehouse">WH-FINAL</td>
        </tr>
    </tbody>
</table>
"""


@pytest.fixture
def mock_proxy_pool():
    """Fixture to mock the ProxyPool and its sessions."""
    # We patch the async classmethod `from_db` separately.
    with patch("parser.stparts_pipeline.ProxyPool.from_db", new_callable=AsyncMock) as mock_from_db:
        # This is the mock for the ProxyPool *instance*.
        mock_pool_instance = MagicMock()

        # This is the mock for the ProxySession instance.
        mock_session = MagicMock()
        mock_session.fetch_html = AsyncMock()

        # Configure the pool instance mock.
        mock_pool_instance.acquire.return_value = mock_session
        mock_pool_instance.close_all = AsyncMock()

        # Make the `from_db` classmethod return our mock pool instance.
        mock_from_db.return_value = mock_pool_instance

        yield mock_pool_instance


@pytest.mark.asyncio
async def test_pipeline_top_10_logic(mock_proxy_pool):
    """Verify that the pipeline correctly filters and returns only the top 10 offers."""
    mock_session = mock_proxy_pool.acquire.return_value
    mock_session.fetch_html.return_value = HTML_FOR_TOP_10_TEST
    articles = ["TESTCODE"]

    results = await run_stparts_pipeline(articles, include_analogs=False)

    assert len(results) == 10
    # Prices are 1.00 to 15.00, so the top 10 should have a max price of 10.00
    assert max(r.price for r in results) == 10.0
    assert min(r.price for r in results) == 1.0


@pytest.mark.asyncio
async def test_pipeline_follows_redirect_link(mock_proxy_pool):
    """Verify that the pipeline follows the 'Показать все варианты' link."""
    mock_session = mock_proxy_pool.acquire.return_value

    async def fetch_side_effect(url, params=None):
        if url == "https://stparts.ru/search":
            return HTML_WITH_REDIRECT_LINK
        elif url == "https://stparts.ru/final-results-page":
            return HTML_FINAL_RESULTS
        return ""

    mock_session.fetch_html.side_effect = fetch_side_effect
    articles = ["TESTCODE"]

    results = await run_stparts_pipeline(articles, include_analogs=False)

    assert mock_session.fetch_html.call_count == 2
    # First call is to the initial search page
    assert mock_session.fetch_html.call_args_list[0].kwargs["params"] == {"pcode": "TESTCODE"}
    # Second call is to the redirect link
    assert mock_session.fetch_html.call_args_list[1].args[0] == "https://stparts.ru/final-results-page"
    assert len(results) == 1
    assert results[0].price == 99.0


@pytest.mark.asyncio
async def test_pipeline_reports_progress(mock_proxy_pool):
    """Verify that the pipeline reports progress correctly and handles concurrency."""
    mock_session = mock_proxy_pool.acquire.return_value
    mock_session.fetch_html.return_value = HTML_FINAL_RESULTS
    articles = ["CODE1", "CODE2", "CODE3", "CODE4"]
    reporter = MockProgressReporter()

    await run_stparts_pipeline(articles, include_analogs=False, reporter=reporter)

    assert reporter.steps == [
        {"step": "FETCHING", "status": "IN_PROGRESS"},
        {"step": "FILTERING", "status": "IN_PROGRESS"},
        {"step": "FILTERING", "status": "SUCCESS"},
    ]
    # With concurrency, order is not guaranteed, so we sort before comparing.
    assert sorted(reporter.percentages) == [
        ("FETCHING", 25),
        ("FETCHING", 50),
        ("FETCHING", 75),
        ("FETCHING", 100),
    ]


@pytest.mark.asyncio
async def test_pipeline_handles_single_task_failure(mock_proxy_pool):
    """Verify the pipeline continues and reports errors if one article fails."""
    mock_session = mock_proxy_pool.acquire.return_value

    async def fetch_side_effect(url, params=None):
        if params and params.get("pcode") == "FAIL_CODE":
            raise httpx.RequestError("Test failure")
        return HTML_FINAL_RESULTS

    mock_session.fetch_html.side_effect = fetch_side_effect
    articles = ["CODE1", "FAIL_CODE", "CODE3"]
    reporter = MockProgressReporter()

    results = await run_stparts_pipeline(articles, include_analogs=False, reporter=reporter)

    # Should still get results from the two successful calls
    assert len(results) == 2
    # Check that the failure was reported
    failure_step = next((s for s in reporter.steps if s.get("status") == "FAILURE"), None)
    assert failure_step is not None
    assert failure_step["step"] == "FETCHING"
    assert "Test failure" in failure_step["details"]["error"]
    assert failure_step["details"]["article"] == "FAIL_CODE"
