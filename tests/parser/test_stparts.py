from selectolax.parser import HTMLParser

from parser.stparts import parse_stparts

# HTML fixture mimicking the structure of the stparts.ru results table
HTML_FIXTURE = """
<!DOCTYPE html>
<html>
<body>
<table id="searchResultsTable">
    <tbody>
        <!-- Standard Offer -->
        <tr class="resultTr2"
            data-brand="Hyundai-KIA"
            data-output-price="38.07"
            data-availability="243"
            data-deadline="840"
            data-deadline-max="864"
            data-is-analog="0"
            data-is-request-article="1">
            <td class="resultDescription">КОЛЬЦО ФОРСУНКИ МЕТАЛЛИЧЕСКОЕ</td>
            <td class="resultWarehouse">UAE1893</td>
            <td class="resultPrice">38.07 руб.</td>
        </tr>
        <!-- Analog Offer -->
        <tr class="resultTr2"
            data-brand="SomeAnalogBrand"
            data-output-price="25.00"
            data-availability="100"
            data-deadline="240"
            data-is-analog="1"
            data-is-request-article="0">
            <td class="resultDescription">ANALOG RING</td>
            <td class="resultWarehouse">WAREHOUSE2</td>
            <td class="resultPrice">25.00 руб.</td>
        </tr>
        <!-- Offer with missing data -->
                <tr class="resultTr2"
                    data-brand="BrandWithMissingData"
                    data-output-price=""
                    data-availability=""
                    data-deadline=""
                    data-is-analog="0">
                    <td class="resultDescription"></td>
                    <td class="resultWarehouse"></td>
                    <td class="resultPrice"></td>
                </tr>
                <!-- Offer with forgiving numeric formats -->
                <tr class="resultTr2"
                    data-brand="ForgivingBrand"
                    data-output-price="123,45"
                    data-availability=" 50+ "
                    data-deadline-max=" 48h "
                    data-is-analog="0">
                    <td class="resultDescription">Forgiving Item</td>
                    <td class="resultWarehouse">WAREHOUSE3</td>
                    <td class="resultPrice">123,45 руб.</td>
                </tr>
            </tbody>
        </table>
        </body>
        </html>
"""

SEARCH_URL = "https://stparts.ru/search/Hyundai-KIA/0PN1113H52?disableFiltering"


def test_parse_stparts_excludes_analogs_by_default():
    """Verifies that analog offers are excluded when include_analogs is False."""
    tree = HTMLParser(HTML_FIXTURE)
    results = parse_stparts(tree, SEARCH_URL, include_analogs=False)

    assert len(results) == 3
    assert not any(r.is_analog for r in results)


def test_parse_stparts_includes_analogs_when_requested():
    """Verifies that analog offers are included when include_analogs is True."""
    tree = HTMLParser(HTML_FIXTURE)
    results = parse_stparts(tree, SEARCH_URL, include_analogs=True)

    assert len(results) == 4
    assert any(r.is_analog for r in results)


def test_parse_stparts_correctly_parses_standard_offer():
    """Verifies that a standard offer row is parsed into the correct OfferRow model."""
    tree = HTMLParser(HTML_FIXTURE)
    results = parse_stparts(tree, SEARCH_URL, include_analogs=True)
    standard_offer = next((r for r in results if not r.is_analog and r.b == "Hyundai-KIA"), None)

    assert standard_offer is not None
    assert standard_offer.b == "Hyundai-KIA"
    assert standard_offer.a == "0PN1113H52"  # From URL
    assert standard_offer.name == "КОЛЬЦО ФОРСУНКИ МЕТАЛЛИЧЕСКОЕ"
    assert standard_offer.price == 38.07
    assert standard_offer.quantity == 243
    assert standard_offer.provider == "UAE1893"
    assert standard_offer.rating is None
    # ceil(864 / 24) = 36
    assert standard_offer.delivery == 36
    assert not standard_offer.is_analog


def test_parse_stparts_handles_missing_data_gracefully():
    """Verifies that rows with missing attributes are parsed with None values."""
    tree = HTMLParser(HTML_FIXTURE)
    results = parse_stparts(tree, SEARCH_URL, include_analogs=True)
    offer_with_missing_data = next((r for r in results if r.b == "BrandWithMissingData"), None)

    assert offer_with_missing_data is not None
    assert offer_with_missing_data.price is None
    assert offer_with_missing_data.quantity is None
    assert offer_with_missing_data.delivery is None
    assert offer_with_missing_data.name == ""
    assert offer_with_missing_data.provider == ""


def test_parse_stparts_handles_forgiving_numeric_formats():
    """Verifies that numeric values with commas, whitespace, and non-digit chars are parsed correctly."""
    tree = HTMLParser(HTML_FIXTURE)
    results = parse_stparts(tree, SEARCH_URL, include_analogs=True)
    forgiving_offer = next((r for r in results if r.b == "ForgivingBrand"), None)

    assert forgiving_offer is not None
    assert forgiving_offer.price == 123.45
    assert forgiving_offer.quantity == 50
    # ceil(48 / 24) = 2
    assert forgiving_offer.delivery == 2
