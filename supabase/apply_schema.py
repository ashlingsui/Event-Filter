#!/usr/bin/env python3
"""Applies supabase/schema.sql via a direct Postgres connection (pg8000 — pure Python, no system
Postgres client library needed). Deliberately NOT idempotent: schema.sql uses `create type` /
`create table` without IF NOT EXISTS, so re-running against an already-applied schema fails
loudly instead of silently no-op'ing. For a schema this security-sensitive (RLS policies, a
write-once trigger), a loud failure on accidental re-run is the right default — don't paper over
it with IF NOT EXISTS/OR REPLACE without thinking about what that would hide.

TLS is fully verified against Supabase's published CA — see _connection_ssl_context().

Usage:
    # once: Supabase dashboard -> Project Settings -> Database -> SSL Configuration ->
    #       Download certificate -> save as supabase/prod-ca-2021.crt
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
    """Fully-verifying TLS context, trusting Supabase's published CA in addition to the system
    roots.

    Supabase's Postgres endpoints present a chain signed by their own 'Supabase Intermediate 2021
    CA', which is not in the OS/certifi trust stores — so the default context fails. The previous
    version of this function responded by setting check_hostname=False and verify_mode=CERT_NONE,
    on the reasoning that schema.sql contains only non-secret DDL.

    That reasoning was wrong, and the mistake is worth keeping written down: the DDL is not the
    asset at risk. This connection AUTHENTICATES, so SUPABASE_DB_PASSWORD crosses it during the
    handshake. With verification disabled, any party able to intercept the connection can present
    any certificate, complete the handshake, and collect the database password — which reaches
    Postgres as a superuser and bypasses every RLS policy in schema.sql. "The payload is public"
    never justifies an unverified channel that carries a credential.

    The correct fix is to trust the right root, not no root. Supabase publishes the CA certificate
    (Project Settings -> Database -> SSL Configuration -> Download certificate); it is public, not
    a secret, and is committed to the repo so every machine verifies against the same root.
    """
    ca_path = Path(config.SUPABASE_CA_CERT)
    if not ca_path.is_file():
        raise SystemExit(
            "Supabase CA certificate not found at {}.\n\n"
            "Download it from the Supabase dashboard:\n"
            "  Project Settings -> Database -> SSL Configuration -> Download certificate\n"
            "and save it to that path (or set SUPABASE_CA_CERT to point at it).\n\n"
            "The certificate is public, not a credential — commit it so every machine verifies\n"
            "against the same root. TLS verification is NOT optional here: this connection "
            "carries the database password.".format(ca_path)
        )

    # create_default_context() gives check_hostname=True and verify_mode=CERT_REQUIRED, and loads
    # the system roots; load_verify_locations then adds Supabase's CA alongside them.
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(ca_path))
    if not ctx.check_hostname or ctx.verify_mode != ssl.CERT_REQUIRED:
        raise SystemExit("Refusing to connect: TLS context is not fully verifying.")
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
