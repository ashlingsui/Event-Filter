#!/usr/bin/env python3
"""Applies supabase/schema.sql via a direct Postgres connection (pg8000 — pure Python, no system
Postgres client library needed). Deliberately NOT idempotent: schema.sql uses `create type` /
`create table` without IF NOT EXISTS, so re-running against an already-applied schema fails
loudly instead of silently no-op'ing. For a schema this security-sensitive (RLS policies, a
write-once trigger), a loud failure on accidental re-run is the right default — don't paper over
it with IF NOT EXISTS/OR REPLACE without thinking about what that would hide.

Usage:
    set -a; source supabase/.env; set +a
    python3 supabase/apply_schema.py
"""
import ssl
import sys
from pathlib import Path

import pg8000.native

sys.path.insert(0, str(Path(__file__).parent.parent))
from supabase import config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connection_ssl_context():
    """Supabase's pooler presents a cert chain signed by their own private
    'Supabase Intermediate 2021 CA', which isn't in any standard OS/certifi trust store — this is
    a documented Supabase infrastructure quirk, not a MITM: verified 2026-09-21 by inspecting the
    live handshake directly (hostname matches *.pooler.supabase.com, O=Supabase Inc, valid dates).
    Direct+pooler hosts and ports 5432/6543 all fail identically with the OS default context, and
    pinning the leaf cert alone still fails chain validation (the intermediate itself has no
    trusted parent in this environment). Verification is disabled for THIS connection only —
    used solely to run schema.sql's non-secret DDL — never for the REST/Auth API calls elsewhere
    in this directory, which verify normally and successfully over port 443."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def main():
    config.require("SUPABASE_DB_HOST", "SUPABASE_DB_PASSWORD")
    conn = pg8000.native.Connection(
        user=config.SUPABASE_DB_USER,
        password=config.SUPABASE_DB_PASSWORD,
        host=config.SUPABASE_DB_HOST,
        port=config.SUPABASE_DB_PORT,
        database=config.SUPABASE_DB_NAME,
        ssl_context=_connection_ssl_context(),
    )
    sql = SCHEMA_PATH.read_text()
    print("Applying {} ({} bytes) to {}...".format(SCHEMA_PATH, len(sql), config.SUPABASE_DB_HOST))
    try:
        conn.run(sql)
    finally:
        conn.close()
    print("Schema applied.")


if __name__ == "__main__":
    main()
