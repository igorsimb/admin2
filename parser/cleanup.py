"""Contains cleanup logic, such as deleting old export files."""

import os
import time
from pathlib import Path


def delete_old_exports(export_dir: Path, older_than_days: int = 5) -> int:
    """
    Deletes Excel files in the specified directory older than a given number of days.

    Args:
        export_dir: The directory containing the export files.
        older_than_days: The age threshold in days for deleting files.

    Returns:
        The number of files that were deleted.
    """
    if not export_dir.is_dir():
        return 0

    deleted_count = 0
    age_threshold_sec = older_than_days * 24 * 60 * 60
    current_time = time.time()

    for entry in os.scandir(export_dir):
        if entry.is_file() and entry.name.endswith(".xlsx"):
            try:
                file_mod_time = entry.stat().st_mtime
                if (current_time - file_mod_time) > age_threshold_sec:
                    os.remove(entry.path)
                    deleted_count += 1
            except OSError:
                # Ignore errors (e.g., file is locked or permissions issue)
                pass

    return deleted_count