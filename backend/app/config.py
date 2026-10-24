"""Application settings loaded from environment variables and the project .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The .env file lives in the project root and is never committed.
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "lol_draft.db"))
    DEFAULT_PLATFORM = os.getenv("DEFAULT_PLATFORM", "eun1")
    DEFAULT_REGION = os.getenv("DEFAULT_REGION", "europe")
