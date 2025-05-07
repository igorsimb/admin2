# parser complexity



Query:

&#x20;   follow the code starting from `async def start_percentage_cross():` to wherever it leads and analyze the code's complexity from 1 to 100.
\- give it a score of unnecessary complexity and the degree of "legacity" of the code from 1 to 100 (100 being almost impossible to read)
\- how much the code can be simplified (e.g. get rid of the async)
\- how much of the code can be structured better for readability
\- dont' go into too much details yet, don't overwhelm me. We will go step by step.

Context: we will be completely re-writing this functionality and putting it into a Django project. The goal will be simplification, getting rid of unnecessary complexity, de-lecacifying the code. Parser repo will be a separate app in the django project, instead of a separate service.



Response:

# Analysis of `start_percentage_cross` and Related Code

## Complexity and Legacy Scores

* **Unnecessary Complexity Score: 75/100**
* **Legacy Code Score: 80/100**

## Key Observations

1. **Overly Complex Async Implementation**:
   * The code uses async/await patterns but then wraps everything in synchronous loops with `asyncio.get_event_loop().run_until_complete()`, which defeats much of the purpose of async.
   * The `generate_sql_query_percentage` function creates an inner async function `_generate_sql_query_percentage` and then runs it in a loop, adding unnecessary complexity.
2. **Convoluted Data Flow**:
   * The request flow is complex: Flask route → Celery task → async wrapper → process\_data function → SQL queries → Excel file generation.
   * Task management involves both Redis and PostgreSQL for storing PIDs, with duplicate code for saving/removing PIDs.
3. **Mixed Responsibilities**:
   * The code mixes HTTP handling, task management, database operations, and business logic in the same functions.
   * There's no clear separation between the API layer, business logic, and data access.
4. **Configuration Issues**:
   * Hard-coded database credentials in config files (ClickInfo class).
   * Inconsistent environment variable usage between services.
   * Multiple Redis databases (db0, db1) used for different purposes.
5. **Error Handling**:
   * Try/except blocks are used extensively but often just log errors and re-raise them.
   * Error handling is inconsistent across different parts of the codebase.
6. **Legacy Patterns**:
   * Uses YAML files for configuration that could be in a database.
   * Mixes Russian and English in code comments and variable names.
   * Uses outdated file-based approaches (Excel file generation) instead of more modern API responses.

## Simplification Opportunities

1. **Remove Unnecessary Async**:
   * The async/await pattern is being used incorrectly and adds complexity without benefits.
   * Django's synchronous views would be simpler and more appropriate for this use case.
2. **Streamline Data Flow**:
   * Replace Celery with Django's built-in task management or a simpler task queue.
   * Use Django models instead of raw SQL queries.
   * Eliminate the need for Redis by using the database for task status tracking.
3. **Separate Concerns**:
   * Split the code into proper Django apps with clear responsibilities.
   * Create separate services for data processing, API handling, and task management.
   * Use Django's ORM instead of raw SQL queries.
4. **Improve Configuration**:
   * Use Django settings for configuration instead of scattered environment variables.
   * Store sensitive information in environment variables or Django's secrets management.
   * Standardize naming conventions across the application.

## Readability Improvements

1. **Code Organization**:
   * Organize code into logical Django apps (API, tasks, data processing).
   * Use Django's class-based views for API endpoints.
   * Create proper models for data structures.
2. **Naming and Documentation**:
   * Standardize on English for all code, comments, and variable names.
   * Use more descriptive function and variable names.
   * Add proper docstrings and type hints.
3. **Simplify Logic**:
   * Break down complex functions into smaller, more focused ones.
   * Use Django's built-in features instead of custom implementations.
   * Eliminate duplicate code for task management.

## Summary

The`start_percentage_cross`functionality and its related code suffer from unnecessary complexity, poor organization, and outdated patterns. Moving to Django will provide an opportunity to significantly simplify the code by leveraging Django's built-in features for routing, ORM, task management, and configuration. The most significant improvements will come from removing the incorrect async implementation, streamlining the data flow, and properly separating concerns into Django apps with clear responsibilities.

