"""Contains the parsing logic specific to the stparts.ru website."""

import math
import re

from selectolax.parser import HTMLParser, Node

from .http import requested_article
from .types import OfferRow

# Optional sign, digits, optional decimal part with '.' or ',' (e.g., "42", "-7", "3.14", "38,07").
_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _get_node_text(node: Node | None) -> str | None:
    """Safely extracts the text from a node, returning None if the node is missing."""
    if node is None:
        return None
    return node.text().strip()


def _parse_deadline(node: Node) -> int | None:
    """
    Parses the deadline from a row node, converting hours to days.
    It tolerates non-digit characters and whitespace.
    """
    deadline_str = node.attributes.get("data-deadline")
    deadline_max_str = node.attributes.get("data-deadline-max")

    def _hours(hours_str: str | None) -> int | None:
        if not hours_str:
            return None
        match = _NUM_RE.search(hours_str.strip())
        if not match:
            return None
        try:
            # Use float to handle potential decimals in string, then convert to int
            return int(float(match.group(0).replace(",", ".")))
        except (ValueError, TypeError):
            return None

    hours = _hours(deadline_str)
    hours_max = _hours(deadline_max_str)

    if hours is None and hours_max is None:
        return None

    # Use the larger of the two values, ignoring any Nones
    effective_max_hours = max(h for h in (hours, hours_max) if h is not None)
    max_deadline_days = math.ceil(effective_max_hours / 24)
    return max_deadline_days


def _parse_price(node: Node) -> float | None:
    """
    Parses and converts the price from a row node to a float.
    It tolerates common currency formatting like commas and spaces.
    """
    price_str = node.attributes.get("data-output-price")
    if not price_str:
        return None
    # Allow "38,07" and "38 070.00"
    cleaned_price = re.sub(r"\s+", "", price_str).replace(",", ".")
    try:
        return float(cleaned_price)
    except (ValueError, TypeError):
        return None


def _parse_quantity(node: Node) -> int | None:
    """
    Parses and converts the quantity from a row node to an integer.
    It extracts numeric values from strings like "50+" or " 100 ".
    """
    quantity_str = node.attributes.get("data-availability")
    if not quantity_str:
        return None
    match = _NUM_RE.search(quantity_str.strip())
    if not match:
        return None
    try:
        return int(float(match.group(0).replace(",", ".")))
    except (ValueError, TypeError):
        return None


def parse_stparts(tree: HTMLParser, source_url: str, include_analogs: bool) -> list[OfferRow]:
    """
    Parses the HTML content from an stparts.ru search results page into a list of OfferRow objects.

    Args:
        tree: A pre-parsed selectolax HTMLParser object of the page.
        source_url: The URL from which the HTML was fetched, used to extract the article code.
        include_analogs: A boolean flag to indicate whether to include analog parts in the results.

    Returns:
        A list of Pydantic OfferRow models representing the parsed offers.
    """
    row_selector = "tbody > tr.resultTr2"
    desc_selector = "td.resultDescription"
    warehouse_selector = "td.resultWarehouse"  # aka provider
    results: list[OfferRow] = []

    try:
        article = requested_article(source_url)
    except ValueError:
        return []

    table = tree.css_first("table#searchResultsTable")
    if not table:
        return []

    for row_node in table.css(row_selector):
        is_analog = row_node.attributes.get("data-is-analog") == "1"
        if not include_analogs and is_analog:
            continue

        # Try to get brand from the `data-brand` attribute first as a fallback.
        brand = row_node.attributes.get("data-brand")
        if not brand:
            # The primary, more reliable location is the text within the resultBrand cell.
            brand_node = row_node.css_first("td.resultBrand a")
            if brand_node:
                brand = brand_node.text(strip=True)

        offer = OfferRow(
            b=brand,
            a=article,
            name=_get_node_text(row_node.css_first(desc_selector)),
            price=_parse_price(row_node),
            quantity=_parse_quantity(row_node),
            provider=_get_node_text(row_node.css_first(warehouse_selector)),
            rating=None,
            delivery=_parse_deadline(row_node),
            is_analog=is_analog,
        )
        results.append(offer)

    return results
