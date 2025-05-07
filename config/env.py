import os
from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent

# Get the environment name from an environment variable, default to staging
ENVIRONMENT = os.environ.get("DJANGO_ENVIRONMENT", "staging")

# Load the appropriate .env file
if ENVIRONMENT == "production":
    env.read_env(BASE_DIR / ".env.production")
else:
    env.read_env(BASE_DIR / ".env.staging")
