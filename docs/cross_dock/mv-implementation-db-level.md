# Materialized View Implementation Plan for Cross-Dock Query Optimization

> **Note**: This document has been updated based on further analysis and discussion. The final implementation approach is documented in [GitHub issue #12](https://github.com/igorsimb/admin2/issues/12).

> **Update (2024-06):**
> - The MV (`sup_stat.mv_cross_dock`) and its query logic have been validated: for all tested (brand, sku) pairs, the MV query produces identical results to the original, but is significantly faster (8x+ for large data sets).
> - A new UI button for the MV-based query will be added, with the old button retained for fallback and comparison during transition.
> - Backend logic will allow routing requests to either the old or MV query, with pseudocode.
> - See the new `mv-implementation-code-level.md` for frontend/backend implementation details.

## 1. Overview

This document outlines the implementation plan for creating a Materialized View to optimize the `query_supplier_data` function in the Cross-Dock application. The current implementation performs complex queries directly against the ClickHouse database, which can be slow for large datasets and creates unnecessary load on the database server.

By implementing a Materialized View, we can:
1. Significantly improve query performance
2. Reduce load on the ClickHouse server
3. Provide more consistent response times
4. Enable more complex queries without performance penalties

## 2. Current Implementation Analysis

### 2.1. Current Query Structure

The current implementation in `clickhouse_service.py` executes two separate queries:

1. First query: Retrieves supplier IDs from the `sup_stat.sup_list` table based on the selected supplier list
2. Second query: Uses these supplier IDs to query price data from `sup_stat.dif_step_1` with complex filtering and sorting

The second query is particularly complex, using:
- Common Table Expressions (CTEs)
- Window functions (ROW_NUMBER)
- Multiple filtering conditions
- Sorting and limiting

This approach has several drawbacks:
- Each query is executed independently for every request
- No caching mechanism exists
- The complex query structure is executed repeatedly
- Performance degrades as data volume increases

### 2.2. Performance Bottlenecks

The main performance bottlenecks in the current implementation are:

1. **Multiple Database Roundtrips**: Two separate queries require multiple network roundtrips
2. **Complex Query Execution**: The window functions and CTEs are computationally expensive
3. **No Data Caching**: Results are not cached between requests
4. **Full Table Scans**: Without proper materialization, the database may perform full table scans

## 3. Materialized View Solution

### 3.1. What is a Materialized View?

A Materialized View is a database object that contains the results of a query. Unlike regular views, materialized views store the result set physically, allowing for faster data retrieval. The view can be refreshed periodically to ensure data is up-to-date.

In ClickHouse, Materialized Views are implemented as special tables that are automatically updated when the source data changes.

### 3.2. Proposed Materialized View Structure

We will create a Materialized View named `mv_cross_dock` that pre-computes and stores the most relevant supplier pricing data. The view will:

1. Join the `sup_stat.sup_list` and `sup_stat.dif_step_1` tables
2. Pre-filter the data (positive quantities, recent data)
3. Store the results in a format optimized for quick retrieval
4. Automatically remove data older than 5 days using TTL

#### Materialized View Schema

```sql
CREATE MATERIALIZED VIEW sup_stat.mv_cross_dock
ENGINE = ReplacingMergeTree()
ORDER BY (supplier_list, brand_lower, sku_lower, supplier_name)
TTL update_date + INTERVAL 5 DAY
POPULATE AS
SELECT
    sl.name AS supplier_name,
    arrayElement(sl.lists, 1) AS supplier_list,
    lower(df.b) AS brand_lower,
    lower(df.a) AS sku_lower,
    df.p AS price,
    df.q AS quantity,
    df.dateupd AS update_date
FROM
    sup_stat.dif_step_1 AS df
INNER JOIN
    sup_stat.sup_list AS sl
ON
    df.supid = sl.dif_id
WHERE
    df.q > 0 AND
    df.dateupd >= now() - interval 5 day
```

### 3.3. Integration with Existing Code

The `query_supplier_data` function will be updated to query the Materialized View instead of executing the complex queries directly:

```python
def query_supplier_data(brand: str, sku: str, supplier_list: str, days_lookback: int = 2) -> pd.DataFrame:
    """
    Query ClickHouse for supplier data for a specific brand and SKU using the Materialized View.

    Args:
        brand: Product brand
        sku: Product SKU (Stock Keeping Unit) - equivalent to article number in the database
        supplier_list: Supplier list to query (e.g., 'Группа для проценки ТРЕШКА', 'ОПТ-2')
        days_lookback: Number of days to look back for supplier data (default: 2)

    Returns:
        DataFrame with supplier data sorted by price (price, quantity, supplier_name)
        Limited to 3 suppliers maximum
    """
    logger.info(
        f"Querying supplier data for {brand}/{sku} with supplier list {supplier_list}, days_lookback={days_lookback}"
    )

    empty_df = pd.DataFrame(columns=["price", "quantity", "supplier_name"])

    try:
        # Special handling for Hyundai/Kia brands which can appear under multiple names
        if brand.lower() in ["hyundai/kia/mobis", "hyundai/kia"]:
            brand_values = ["hyundai/kia", "hyundai/kia/mobis"]
        else:
            brand_values = [brand.lower()]

        # Query the materialized view directly
        query = """
        SELECT
            price,
            quantity,
            supplier_name
        FROM
        (
            -- Subquery to rank suppliers by price
            SELECT
                price,
                quantity,
                supplier_name,
                -- Rank suppliers by price within each brand/SKU combination
                ROW_NUMBER() OVER (PARTITION BY brand_lower, sku_lower ORDER BY price ASC) AS rank
            FROM
                sup_stat.mv_cross_dock
            WHERE
                supplier_list = %(supplier_list)s AND
                sku_lower = %(sku_lower)s AND
                brand_lower IN %(brand_values)s AND
                update_date >= now() - interval %(days_lookback)s day
        )
        WHERE rank <= 3
        ORDER BY price ASC
        """

        query_params = {
            "sku_lower": sku.lower(),
            "brand_values": brand_values,
            "supplier_list": supplier_list,
            "days_lookback": days_lookback,
        }

        with get_clickhouse_client() as client:
            logger.info(
                f"Executing materialized view query with params: sku={sku.lower()}, brands={brand_values}, supplier_list={supplier_list}, days_lookback={days_lookback}"
            )
            result = client.execute(query, query_params)
            logger.info(f"Query executed successfully, got {len(result)} results")

        if result:
            result_df = pd.DataFrame(result, columns=["price", "quantity", "supplier_name"])
            logger.info(f"Created DataFrame with {len(result_df)} rows")
        else:
            result_df = empty_df
            logger.warning(f"No results found for {brand}/{sku} with supplier list {supplier_list}")

        return result_df

    except Exception as e:
        logger.exception(f"Error querying supplier data: {e}")
        return empty_df
```

> **Update (2024-06):**
> - The MV query has been validated for all tested (brand, sku) pairs: results are identical to the original query, with major performance improvements.
> - The application will soon provide two UI buttons: one for the old query, one for the MV-based query, to allow comparison and fallback.
> - Backend logic will route requests based on which button is pressed. Example pseudocode:
>   ```python
>   if use_mv:
>       run_mv_query(...)
>   else:
>       run_old_query(...)
>   ```
> - See `mv-implementation-code-level.md` for full implementation plan.

### 3.4. Fallback Mechanism

To ensure reliability, we'll implement a fallback mechanism that uses the original query if the Materialized View query fails:

```python
def query_supplier_data(brand: str, sku: str, supplier_list: str, days_lookback: int = 2) -> pd.DataFrame:
    """
    Query ClickHouse for supplier data using the Materialized View with fallback to original query.
    """
    try:
        # Try using the materialized view first
        return query_supplier_data_mv(brand, sku, supplier_list, days_lookback)
    except Exception as e:
        logger.warning(f"Materialized view query failed: {e}. Falling back to original query.")
        messages.warning(f"Materialized view query failed: {e}. Falling back to original query.")
        # Fall back to the original query implementation
        return query_supplier_data_original(brand, sku, supplier_list, days_lookback)
```

## 4. Database Schema Changes

### 4.1. Creating the Materialized View

The following SQL will be used to create the Materialized View in ClickHouse:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS sup_stat.mv_cross_dock
ENGINE = ReplacingMergeTree()
ORDER BY (supplier_list, brand_lower, sku_lower, supplier_name)
TTL update_date + INTERVAL 5 DAY
POPULATE AS
SELECT
    sl.name AS supplier_name,
    arrayElement(sl.lists, 1) AS supplier_list,
    lower(df.b) AS brand_lower,
    lower(df.a) AS sku_lower,
    df.p AS price,
    df.q AS quantity,
    df.dateupd AS update_date
FROM
    sup_stat.dif_step_1 AS df
INNER JOIN
    sup_stat.sup_list AS sl
ON
    df.supid = sl.dif_id
WHERE
    df.q > 0 AND
    df.dateupd >= now() - interval 5 day;
```

### 4.2. Refreshing the Materialized View

In ClickHouse, Materialized Views are automatically updated when the source tables change. However, we'll also implement a manual refresh mechanism for maintenance purposes:

```sql
-- Manual refresh if needed
-- Option 1: Optimize table to force merges and apply TTL
OPTIMIZE TABLE sup_stat.mv_cross_dock FINAL;

-- Option 2: Recreate the materialized view (more disruptive but ensures fresh data)
DROP TABLE IF EXISTS sup_stat.mv_cross_dock;
-- Then recreate using the CREATE MATERIALIZED VIEW statement above
```

## 5. Performance Considerations

### 5.1. Expected Performance Improvements

Based on similar implementations, we can expect:
- 10-100x faster query execution time
- Reduced CPU and memory usage on the ClickHouse server
- More consistent response times, especially under load
- Better scalability for concurrent requests

### 5.2. Storage Requirements

The Materialized View will require additional storage space. Estimated storage requirements:
- Approximately 10-20% of the size of the source tables
- For a 100GB source dataset, expect 10-20GB for the Materialized View

### 5.3. Refresh Overhead and Data Aging

The automatic refresh process will create some overhead on the database server:
- Incremental updates should be efficient for most changes
- Major data changes might cause temporary performance degradation during refresh
- The TTL clause will automatically remove data older than 5 days
- Consider scheduling OPTIMIZE TABLE commands during off-peak hours to ensure optimal performance

## 6. Implementation Steps

### 6.1. Development Phase

1. **Create Test Materialized View**
   - Create the view in a development/staging environment
   - Verify the view structure and data accuracy
   - Test query performance

2. **Update Code**
   - Refactor `clickhouse_service.py` to use the Materialized View
   - Implement the fallback mechanism
   - Add logging for performance monitoring

3. **Write Tests**
   - Create unit tests for the new query function
   - Test the fallback mechanism
   - Benchmark performance against the original implementation

> **Update (2024-06):**
> - Validation complete: MV and old queries produce identical results for all tested cases.
> - Next: Add new UI button for MV query, retain old button for fallback/comparison.
> - Backend will support routing to either query.
> - See `mv-implementation-code-level.md` for details.

### 6.2. Deployment Phase

1. **Create Materialized View in Production**
   - Execute the CREATE MATERIALIZED VIEW statement
   - Monitor the initial population process
   - Verify data accuracy

2. **Deploy Code Changes**
   - Deploy the updated `clickhouse_service.py`
   - Enable feature with a feature flag if possible
   - Monitor for errors or performance issues

3. **Validate Results**
   - Compare query results between old and new implementations
   - Verify performance improvements
   - Check for any discrepancies in data

### 6.3. Monitoring and Maintenance

1. **Performance Monitoring**
   - Track query execution times
   - Monitor ClickHouse server load
   - Set up alerts for performance degradation

2. **Data Validation**
   - Periodically compare results with the original query
   - Check for data staleness or inconsistencies
   - Implement automated validation tests

3. **Maintenance Tasks**
   - Schedule regular view refreshes if needed
   - Monitor storage usage
   - Optimize the view structure based on usage patterns

## 7. Rollback Plan

In case of issues with the Materialized View implementation, we have the following rollback options:

1. **Code-Level Rollback**
   - The fallback mechanism allows automatic rollback to the original query
   - If needed, disable the Materialized View usage in code

2. **Database-Level Rollback**
   - If the Materialized View causes database issues:
   ```sql
   DROP MATERIALIZED VIEW IF EXISTS sup_stat.mv_cross_dock;
   ```

## 8. Timeline

| Phase | Task | Estimated Time |
|-------|------|----------------|
| Development | Create Test Materialized View | 1 day |
| Development | Update Code | 1 day |
| Development | Write Tests | 1 day |
| Testing | Performance Testing | 1 day |
| Deployment | Create Production View | 1 day |
| Deployment | Deploy Code Changes | 1 day |
| Validation | Monitor and Validate | 2 days |
| **Total** | | **8 days** |

## 9. Conclusion

Implementing a Materialized View for the `query_supplier_data` function will significantly improve performance and reduce database load. The proposed implementation provides a balance between performance optimization and reliability, with a fallback mechanism to ensure continuous operation.

This approach aligns with best practices for database optimization and will provide a solid foundation for future enhancements to the Cross-Dock functionality.

## 10. Final Implementation Approach

After further analysis and discussion, the final implementation approach has been refined to use a Simplified Materialized View with TTL. This approach:

- Uses a ReplacingMergeTree engine for better handling of updates
- Includes a TTL clause to automatically remove data older than 5 days
- Performs the final ranking and limiting (top 3 suppliers) at query time rather than in the materialized view
- Ensures results identical to the original query while maintaining performance benefits

> **Update (2024-06):**
> - MV is validated and ready for production use, with fallback to old query as needed.
> - UI and backend changes are planned to allow seamless transition and comparison.
> - Documentation and migration plan will be updated as the rollout proceeds.
> - See `mv-implementation-code-level.md` for code-level implementation plan.

### 10.1 Key Differences from Initial Approach

The final approach differs from the initial proposal in several important ways:

1. **Engine Change**: Using ReplacingMergeTree instead of MergeTree for better handling of updates
2. **TTL Implementation**: Adding automatic data aging with TTL clause
3. **Ranking Strategy**: Moving the ranking logic to query time instead of pre-computing it in the view
4. **Maintenance Strategy**: Using OPTIMIZE TABLE commands instead of manual INSERT refreshes

### 10.2 Implementation Details

The complete implementation details, including the final SQL definition and optimized query, are documented in [GitHub issue #12](https://github.com/igorsimb/admin2/issues/12).