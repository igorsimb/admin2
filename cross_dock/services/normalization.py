"""Normalize uploaded cross-dock pairs using the shared supplier brand dictionary.

The source and RMV already store canonical uppercase values. Resolve input aliases
through dif.zap_brand_cross and dif.unique_brands, as in admin_flask. Unknown brands
fall back to uppercase; database failures and conflicting mappings fail the report.
"""

from collections import defaultdict

from common.utils.clickhouse import get_clickhouse_client


def normalize_brand_sku_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Preserve input order and duplicates while resolving brands and uppercasing SKUs."""
    cleaned = [(brand.strip().upper(), sku.strip().upper()) for brand, sku in pairs]
    brands = sorted({brand for brand, sku in cleaned if brand and sku})
    if not brands:
        return cleaned

    with get_clickhouse_client() as client:
        rows = client.query(
            """
            SELECT DISTINCT upperUTF8(trimBoth(brand)), parent_id
            FROM dif.zap_brand_cross
            WHERE upperUTF8(replaceAll(trimBoth(brand), ' ', '')) IN %(brand_keys)s
            """,
            parameters={"brand_keys": tuple(sorted({brand.replace(" ", "") for brand in brands}))},
        ).result_rows
        parent_ids = tuple(sorted({parent_id for _, parent_id in rows if parent_id is not None}))
        canonical_rows = (
            client.query(
                "SELECT DISTINCT id, brand FROM dif.unique_brands WHERE id IN %(parent_ids)s",
                parameters={"parent_ids": parent_ids},
            ).result_rows
            if parent_ids
            else []
        )

    canonical_by_id = {}
    for parent_id, canonical in canonical_rows:
        canonical = str(canonical).strip().upper() if canonical is not None else ""
        if not canonical or canonical_by_id.get(parent_id, canonical) != canonical:
            raise ValueError(f"Conflicting or empty canonical brand for id {parent_id}")
        canonical_by_id[parent_id] = canonical

    exact = defaultdict(set)
    compact = defaultdict(set)
    for alias, parent_id in rows:
        if parent_id is None:
            continue
        if parent_id not in canonical_by_id:
            raise ValueError(f"Missing canonical brand for id {parent_id}")
        alias = str(alias).strip().upper()
        canonical = canonical_by_id[parent_id]
        exact[alias].add(canonical)
        compact[alias.replace(" ", "")].add(canonical)

    mapping = {}
    for brand in brands:
        candidates = exact.get(brand) or compact.get(brand.replace(" ", ""), set())
        if len(candidates) > 1:
            raise ValueError(f"Conflicting brand normalization for {brand!r}: {sorted(candidates)}")
        mapping[brand] = next(iter(candidates)) if candidates else brand
    return [(mapping.get(brand, brand), sku) for brand, sku in cleaned]
