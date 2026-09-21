"""Minimal Supabase REST (PostgREST) + Auth (GoTrue) client — raw HTTP via requests, no SDK
dependency, consistent with the rest of this codebase. Two distinct roles matter here:

  service role  — bypasses RLS entirely. Used by the pipeline (push_events.py, migrate_outcomes.py)
                  and by this module's admin_* functions. Never ships to a browser.
  a signed-in user's own access_token — respects RLS exactly as a real logged-in user would. This
                  is the ONLY way to genuinely test the privacy boundary; querying with the service
                  role proves nothing about RLS since it bypasses RLS by definition.
"""
import requests

from . import config


class SupabaseClient:
    def __init__(self, url, api_key, access_token=None):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.access_token = access_token or api_key

    def _headers(self, prefer=None):
        headers = {
            "apikey": self.api_key,
            "Authorization": "Bearer {}".format(self.access_token),
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def select(self, table, params=None):
        resp = requests.get(
            "{}/rest/v1/{}".format(self.url, table),
            headers=self._headers(), params=params or {}, timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def insert(self, table, rows, returning=True):
        prefer = "return=representation" if returning else "return=minimal"
        resp = requests.post(
            "{}/rest/v1/{}".format(self.url, table),
            headers=self._headers(prefer=prefer), json=rows, timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if returning else None

    def upsert(self, table, rows, on_conflict=None, returning=True):
        params = {"on_conflict": on_conflict} if on_conflict else {}
        prefer = "resolution=merge-duplicates" + (",return=representation" if returning else ",return=minimal")
        resp = requests.post(
            "{}/rest/v1/{}".format(self.url, table),
            headers=self._headers(prefer=prefer), params=params, json=rows, timeout=30,
        )
        resp.raise_for_status()
        return resp.json() if returning else None

    def update(self, table, params, patch, returning=True):
        prefer = "return=representation" if returning else "return=minimal"
        resp = requests.patch(
            "{}/rest/v1/{}".format(self.url, table),
            headers=self._headers(prefer=prefer), params=params, json=patch, timeout=20,
        )
        resp.raise_for_status()
        return resp.json() if returning else None

    def delete(self, table, params):
        resp = requests.delete(
            "{}/rest/v1/{}".format(self.url, table),
            headers=self._headers(), params=params, timeout=20,
        )
        resp.raise_for_status()

    def rpc(self, function_name, args=None):
        resp = requests.post(
            "{}/rest/v1/rpc/{}".format(self.url, function_name),
            headers=self._headers(), json=args or {}, timeout=60,
        )
        resp.raise_for_status()
        return resp.json() if resp.text else None


def service_client():
    config.require("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    return SupabaseClient(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def user_client(access_token):
    config.require("SUPABASE_URL", "SUPABASE_ANON_KEY")
    return SupabaseClient(config.SUPABASE_URL, config.SUPABASE_ANON_KEY, access_token=access_token)


def anon_client():
    """No signed-in user at all — for verifying that a fully unauthenticated request also sees
    nothing private (auth.uid() is null, which every own-row policy requires to be non-null)."""
    config.require("SUPABASE_URL", "SUPABASE_ANON_KEY")
    return SupabaseClient(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)


def admin_create_user(email, password):
    """GoTrue admin endpoint, service role only. For disposable test users (test_rls.py) — not
    part of the product's own sign-up flow, which is client-side supabase-js email/Google
    sign-up per SPEC.md §5 and lives in the frontend, not here."""
    config.require("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    resp = requests.post(
        "{}/auth/v1/admin/users".format(config.SUPABASE_URL.rstrip("/")),
        headers={
            "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": "Bearer {}".format(config.SUPABASE_SERVICE_ROLE_KEY),
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password, "email_confirm": True},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def admin_delete_user(user_id):
    config.require("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    resp = requests.delete(
        "{}/auth/v1/admin/users/{}".format(config.SUPABASE_URL.rstrip("/"), user_id),
        headers={
            "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": "Bearer {}".format(config.SUPABASE_SERVICE_ROLE_KEY),
        },
        timeout=20,
    )
    resp.raise_for_status()


def sign_in(email, password):
    """Password sign-in against the anon key. Returns GoTrue's session payload; ["access_token"]
    is the JWT that RLS policies actually evaluate auth.uid() against."""
    config.require("SUPABASE_URL", "SUPABASE_ANON_KEY")
    resp = requests.post(
        "{}/auth/v1/token".format(config.SUPABASE_URL.rstrip("/")),
        params={"grant_type": "password"},
        headers={"apikey": config.SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()
