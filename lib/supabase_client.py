"""Supabase client wrapper. Falls back to in-memory dict cache if env not set.
This keeps the app RUNNING even without Supabase configured (dev/test mode).
"""
import os
import time
from datetime import datetime

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

# Bump this to invalidate ALL cached searches after a backend query/format
# change (e.g. the trending 'stars:>5000' fix). Old cached result sets that
# were fetched with the previous (buggy) query are ignored once this changes.
CACHE_VERSION = "v2"

def _ver_key(key):
    return key + "::" + CACHE_VERSION

TTL = 10 * 60  # 10 minutes

# Per-repo AI-verdict TTL. The search-result cache (TTL above) is unchanged;
# this ONLY governs how long a computed AI verdict stays valid before it is
# re-verified on the next /api/verify call. 30 days.
VERDICT_TTL = 30 * 24 * 60 * 60


def _parse_ts(value):
    """Tolerant parse of a stored timestamp into epoch seconds.
    Accepts ISO strings (with/without 'Z'/'T'), Postgres timestamptz, or
    None/empty -> 0 (treated as infinitely old, i.e. expired)."""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("Z", "").replace("T", " ")
    if "." in s:  # chop fractional seconds
        s = s.split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M"):
        try:
            return time.mktime(time.strptime(s, fmt)) - time.timezone
        except Exception:
            continue
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def get_cached_search(query):
    key = _ver_key(query)
    if _client:
        try:
            res = (_client.table("search_cache").select("*")
                   .eq("query", key).execute())
            if res.data:
                row = res.data[0]
                if row["expires_at"] and time.time() < _iso_to_ts(row["expires_at"]):
                    return row["results"]
        except Exception:
            pass
    # memory fallback
    row = _MEM_CACHE.get(key)
    if row and time.time() < row["expires_at"]:
        return row["results"]
    return None


def set_cached_search(query, results):
    key = _ver_key(query)
    expires = time.time() + TTL
    if _client:
        try:
            _client.table("search_cache").upsert({
                "query": key, "results": results,
                "cached_at": _now_iso(), "expires_at": _ts_to_iso(expires)
            }).execute()
            return
        except Exception:
            pass
    _MEM_CACHE[key] = {"results": results, "expires_at": expires}


# In-memory fallback for NL cache (lost on restart, fine for dev)
_MEM_NL = {}


def get_nl_cache(raw_query):
    """Return cached (query_variants, ranked_order) or None.
    ranked_order may be None if only the translation was cached."""
    if _client:
        try:
            res = (_client.table("nl_query_cache").select("*")
                   .eq("raw_query", raw_query).execute())
            if res.data:
                row = res.data[0]
                return row.get("query_variants"), row.get("ranked_order")
        except Exception:
            pass
    row = _MEM_NL.get(raw_query)
    if row:
        return row.get("query_variants"), row.get("ranked_order")
    return None, None


def set_nl_cache(raw_query, query_variants, ranked_order=None):
    """Upsert NL translation (+optional ranking) into cache."""
    if _client:
        try:
            _client.table("nl_query_cache").upsert({
                "raw_query": raw_query,
                "query_variants": query_variants,
                "ranked_order": ranked_order,
                "cached_at": _now_iso(),
            }).execute()
            return
        except Exception:
            pass
    _MEM_NL[raw_query] = {"query_variants": query_variants, "ranked_order": ranked_order}


def get_verified(owner, name):
    key = f"{owner}/{name}"
    if _client:
        try:
            res = (_client.table("verified_repos").select("*")
                   .eq("owner", owner).eq("name", name).execute())
            if res.data:
                row = res.data[0]
                row["verified_at"] = _verified_at_iso(row.get("verified_at"))
                return row
        except Exception:
            pass
    return _MEM_VERIFIED.get(key)


def _verified_at_iso(value):
    """Return the verdict timestamp as an ISO 8601 string for the frontend.
    Supabase returns timestamptz columns as Python datetime objects, so we
    handle both datetime and string inputs. Falls back to now() if missing."""
    if not value:
        return _now_iso()
    if isinstance(value, str):
        return value  # already an ISO string
    if hasattr(value, "isoformat"):  # datetime / related
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        return _ts_to_iso(float(value))
    except Exception:
        return _now_iso()


def set_verified(owner, name, verdict, summary, provider, stars,
                 maintained=None, maturity=None, community=None, docs=None,
                 setup=None, reasoning=None, model=None):
    row = {"owner": owner, "name": name, "verdict": verdict,
           "summary": summary, "ai_provider": provider,
           "verified_at": _now_iso(),
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
    # Naive ISO (no 'Z') — the live Supabase columns are TIMESTAMP (without
    # tz), which rejects the 'Z' suffix. Render runs in UTC, so naive UTC
    # strings are consistent. Frontend display adds 'Z' where needed.
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _ts_to_iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))


def _iso_to_ts(iso):
    """Robust parse of a stored timestamp into epoch seconds.
    Handles Supabase-returned datetime objects, ISO strings with/without 'Z'
    and with/without 'T'. None/0 -> 0 (treated as expired)."""
    if not iso:
        return 0
    if isinstance(iso, (int, float)):
        return float(iso)
    if hasattr(iso, "timestamp"):  # datetime / related
        try:
            return iso.timestamp()
        except Exception:
            pass
    s = str(iso).strip().replace("Z", "").replace("T", " ")
    if "." in s:  # chop fractional seconds
        s = s.split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M"):
        try:
            return time.mktime(time.strptime(s, fmt)) - time.timezone
        except Exception:
            continue
    return 0
