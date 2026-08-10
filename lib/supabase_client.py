"""Supabase client wrapper. Falls back to in-memory dict cache if env not set.
This keeps the app RUNNING even without Supabase configured (dev/test mode).
"""
import os
import time

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        _client = None

# In-memory fallback (lost on restart, fine for dev)
_MEM_CACHE = {}
_MEM_VERIFIED = {}

TTL = 10 * 60  # 10 minutes


def get_cached_search(query):
    if _client:
        try:
            res = (_client.table("search_cache").select("*")
                   .eq("query", query).execute())
            if res.data:
                row = res.data[0]
                if row["expires_at"] and time.time() < _iso_to_ts(row["expires_at"]):
                    return row["results"]
        except Exception:
            pass
    # memory fallback
    row = _MEM_CACHE.get(query)
    if row and time.time() < row["expires_at"]:
        return row["results"]
    return None


def set_cached_search(query, results):
    expires = time.time() + TTL
    if _client:
        try:
            _client.table("search_cache").upsert({
                "query": query, "results": results,
                "cached_at": _now_iso(), "expires_at": _ts_to_iso(expires)
            }).execute()
            return
        except Exception:
            pass
    _MEM_CACHE[query] = {"results": results, "expires_at": expires}


def get_verified(owner, name):
    key = f"{owner}/{name}"
    if _client:
        try:
            res = (_client.table("verified_repos").select("*")
                   .eq("owner", owner).eq("name", name).execute())
            if res.data:
                return res.data[0]
        except Exception:
            pass
    return _MEM_VERIFIED.get(key)


def set_verified(owner, name, verdict, summary, provider, stars,
                 maintained=None, maturity=None, community=None, docs=None,
                 setup=None, reasoning=None, model=None):
    row = {"owner": owner, "name": name, "verdict": verdict,
           "summary": summary, "ai_provider": provider,
           "github_stars_at_time": stars,
           "model": model or provider,
           "maintained": maintained, "maturity": maturity,
           "community": community, "docs": docs, "setup": setup,
           "reasoning": reasoning}
    if _client:
        try:
            _client.table("verified_repos").upsert(row, on_conflict="owner,name").execute()
            return
        except Exception:
            pass
    _MEM_VERIFIED[f"{owner}/{name}"] = row


def keepalive():
    if _client:
        try:
            _client.table("keepalive_log").insert({"pinged_at": _now_iso()}).execute()
            return True
        except Exception:
            return False
    return True  # memory mode: nothing to ping


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ts_to_iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _iso_to_ts(iso):
    try:
        return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    except Exception:
        return 0
