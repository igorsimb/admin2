"""Handles the creation of wide top-10 Excel reports from parsed data."""

from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

import pandas as pd

from .types import OfferRow


def pivot_offers_for_export(offers: Iterable[OfferRow]) -> pd.DataFrame:
    """
    Pivots a list of OfferRow objects into a wide DataFrame suitable for Excel export.

    The pipeline has already sorted and selected the top 10 offers per article.
    This function transforms that long-format data into a wide format where each
    row represents a unique article and columns represent the top 10 offers.

    Args:
        offers: An iterable of OfferRow objects, pre-sorted and filtered.

    Returns:
        A pandas DataFrame in the specified wide format.
    """
    # Define column order to ensure consistency, even for empty dataframes
    columns = ["brand", "article"]
    for i in range(1, 11):
        columns.extend([f"price {i}", f"supplier {i}", f"quantity {i}", f"rating {i}", f"name {i}"])

    offers_list = list(offers)
    if not offers_list:
        return pd.DataFrame(columns=columns)

    # Group offers by brand and article
    grouped = pd.DataFrame([o.model_dump() for o in offers_list]).groupby(["b", "a"])

    wide_rows = []
    for (brand, article), group in grouped:
        row = {"brand": brand, "article": article}
        # Sort within the group one last time to be certain
        group = group.sort_values(by=["price", "quantity"], ascending=[True, False])
        for i, offer in enumerate(group.head(10).itertuples(), start=1):
            row[f"price {i}"] = offer.price
            row[f"supplier {i}"] = offer.provider
            row[f"quantity {i}"] = offer.quantity
            row[f"rating {i}"] = offer.rating
            row[f"name {i}"] = offer.name
        wide_rows.append(row)

    return pd.DataFrame(wide_rows, columns=columns)


def export_offers_xlsx(run_id: UUID, source: str, df_wide: pd.DataFrame, export_dir: Path) -> Path:
    """
    Writes the wide-format DataFrame to a formatted Excel file.

    Args:
        run_id: The UUID of the run, used for the filename.
        source: The data source name (e.g., "stparts"), used for the sheet name.
        df_wide: The wide-format DataFrame from `pivot_offers_for_export`.
        export_dir: The directory where the Excel file will be saved.

    Returns:
        The path to the newly created Excel file.
    """
    export_path = export_dir / f"stparts_{run_id}.xlsx"
    with pd.ExcelWriter(export_path, engine="xlsxwriter") as writer:
        df_wide.to_excel(writer, sheet_name=source, startrow=1, header=True, index=False)

        workbook = writer.book
        worksheet = writer.sheets[source]

        # --- Formatting --- #
        # Defend against empty dataframe
        num_cols = max(1, len(df_wide.columns))

        # 1. Merged header cell for the source
        merge_format = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "font_size": 14,
            }
        )
        worksheet.merge_range(0, 0, 0, num_cols - 1, f"Source: {source}", merge_format)

        # 2. Price column number format
        price_format = workbook.add_format({"num_format": "#,##0.00"})
        for i, col in enumerate(df_wide.columns):
            if col.startswith("price"):
                # to_excel index=False means our first column is at 0.
                worksheet.set_column(i, i, 12, price_format)

        # 3. Freeze panes at the first data row
        worksheet.freeze_panes(2, 0)

    return export_path
