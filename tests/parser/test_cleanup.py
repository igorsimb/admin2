import os
import time
from pathlib import Path

from parser.cleanup import delete_old_exports


def test_delete_old_exports(tmp_path: Path):
    """Verify that old export files are deleted while new ones are kept."""
    export_dir = tmp_path
    now = time.time()
    age_threshold_sec = 5 * 24 * 60 * 60

    # Create some files
    (export_dir / "new_export_1.xlsx").touch()
    (export_dir / "new_export_2.txt").touch()  # Should be ignored

    old_file_1 = export_dir / "old_export_1.xlsx"
    old_file_2 = export_dir / "old_export_2.xlsx"
    old_file_1.touch()
    old_file_2.touch()

    # Set modification time of old files to be 6 days ago
    six_days_ago = now - (age_threshold_sec + 24 * 60 * 60)
    os.utime(old_file_1, (six_days_ago, six_days_ago))
    os.utime(old_file_2, (six_days_ago, six_days_ago))

    deleted_count = delete_old_exports(export_dir, older_than_days=5)

    assert deleted_count == 2
    assert (export_dir / "new_export_1.xlsx").exists()
    assert (export_dir / "new_export_2.txt").exists()  # Non-xlsx file should not be deleted
    assert not old_file_1.exists()
    assert not old_file_2.exists()


def test_delete_old_exports_no_directory():
    """Verify that the function returns 0 if the directory does not exist."""
    non_existent_dir = Path("/path/to/non_existent_dir")

    deleted_count = delete_old_exports(non_existent_dir)

    assert deleted_count == 0
