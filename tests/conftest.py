import pytest

"""
Global pytest configuration file.

This file configures pytest behavior for all test runs in the project.
It automatically enables verbose mode (-v) for all pytest runs without
having to specify it on the command line.

To disable verbose mode for a specific run, use:
    pytest --no-verbose

This is useful for CI/CD pipelines or when you want less output.
"""


def pytest_addoption(parser):
    """Add command-line options to pytest."""
    parser.addoption(
        "--no-verbose",
        action="store_true",
        default=False,
        help="Disable verbose output (override default verbose mode)",
    )


def pytest_configure(config):
    """Configure pytest before test collection."""
    # If --no-verbose is not specified, add -v to the command line arguments
    if not config.getoption("--no-verbose"):
        config.option.verbose = True


@pytest.fixture(autouse=True)
def _override_celery_settings_for_tests(settings):
    """Force Celery to run synchronously in tests and use a local backend."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_BROKER_URL = "memory://"
    settings.CELERY_RESULT_BACKEND = "django-db"


@pytest.fixture(autouse=True)
# using aaa in name to make sure this fixture always runs first due to some alphabetical order in certain cases
def aaa_db(db):
    pass
