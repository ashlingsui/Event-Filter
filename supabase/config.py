"""Shared Supabase connection config. Reads from environment variables only — never hardcode a
key here. Populate them by sourcing supabase/.env (copy from .env.example) before running any
script in this directory, e.g.:

    set -a; source supabase/.env; set +a
    python3 supabase/apply_schema.py
"""
import os
from pathlib import Path

_ENV_PATH = Path(__file__).parent / ".env"


def _load_dotenv_if_present():
    """Minimal .env loader so scripts work even if the caller forgot to `source` it — doesn't
    override already-set real environment variables."""
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv_if_present()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

SUPABASE_DB_HOST = os.environ.get("SUPABASE_DB_HOST")
SUPABASE_DB_PORT = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
SUPABASE_DB_USER = os.environ.get("SUPABASE_DB_USER", "postgres")
SUPABASE_DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD")
SUPABASE_DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")


def require(*names):
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            "Missing required env var(s): {}. Copy supabase/.env.example to supabase/.env and "
            "fill them in from the Supabase dashboard.".format(", ".join(missing))
        )
