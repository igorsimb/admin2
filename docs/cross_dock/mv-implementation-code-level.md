# Cross-Dock MV Implementation: Code-Level Plan

> **This document describes the detailed implementation plan for frontend and backend logic to support the new Materialized View (MV) supplier query.**
> 
> For database schema and DDL, see: `mv-implementation-db-level.md`.

---

## 1. Overview

The goal is to enable the application to use the new, high-performance MV-based supplier query, while retaining the old query for fallback and comparison. This will be achieved by:
- Adding a new UI button for the MV query
- Retaining the old button for the legacy query
- Updating backend logic to route requests to the appropriate query implementation
- Providing a seamless user experience for comparison and validation

---

## 2. Frontend/UI Implementation

### 2.1. UI Changes
- **Add a new button** (e.g., "Fast Supplier Query (MV)") next to the existing supplier query button.
- **Label the old button** clearly (e.g., "Legacy Supplier Query") to avoid confusion.
- **Display results** from each query in a consistent format, allowing users to compare outputs easily.
- **(Optional)**: Add a visual indicator or tooltip explaining the difference between the two buttons.

### 2.2. User Experience
- Both buttons should be available during the transition period.
- If the MV query fails, display a warning and optionally fall back to the legacy query (with a message to the user).
- Results should be clearly labeled as coming from the MV or legacy query.

### 2.3. UI Pseudocode
```js
// Pseudocode for button event handlers
onLegacyQueryClick = () => runSupplierQuery({ useMV: false });
onMVQueryClick = () => runSupplierQuery({ useMV: true });
```

---

## 3. Backend Implementation

### 3.1. Routing Logic
- Update the backend endpoint that handles supplier queries to accept a flag (e.g., `use_mv`) indicating which query to run.
- Route the request to either the MV-based query or the legacy query based on this flag.
- Implement robust error handling: if the MV query fails, log the error and (optionally) fall back to the legacy query.

### 3.2. Pseudocode
```python
def supplier_query_endpoint(request):
    use_mv = request.json.get("use_mv", False)
    # ... extract other params ...
    if use_mv:
        try:
            return run_mv_query(...)
        except Exception as e:
            log.warning(f"MV query failed: {e}")
            # Optionally: fallback to old query
            return run_legacy_query(...)
    else:
        return run_legacy_query(...)
```

### 3.3. API Changes
- The supplier query API should accept a new parameter (e.g., `use_mv: bool`).
- Response format should remain unchanged for compatibility.
- Add logging to track which query path is used and any errors.

---

## 4. Testing & Validation

### 4.1. UI Testing
- Verify both buttons trigger the correct backend logic.
- Ensure results are displayed correctly and labeled by query type.
- Test error handling and fallback behavior.

### 4.2. Backend Testing
- Unit tests for both query implementations (MV and legacy).
- Tests for routing logic and fallback mechanism.
- Parameterized tests for a variety of (brand, sku, supplier_list) inputs.
- Mock ClickHouse responses to isolate logic.

### 4.3. Integration Testing
- End-to-end tests: simulate user actions and verify correct backend path and results.
- Compare results from both queries for a range of test cases (should be identical).

---

## 5. Rollout & Migration Plan

- **Phase 1:** Deploy with both buttons and backend paths enabled. Monitor usage and correctness.
- **Phase 2:** Once validated, update documentation and communicate the change to users.
- **Phase 3:** Plan to deprecate the legacy query/button after sufficient validation and user feedback.

---

## 6. References
- **DB-level implementation:** See `mv-implementation-db-level.md` for schema, DDL, and performance notes.
- **GitHub issue:** [#12](https://github.com/igorsimb/admin2/issues/12)

---

**No code changes are made yet. This document is for planning and review.** 