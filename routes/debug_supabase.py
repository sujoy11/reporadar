"""TEMPORARY diagnostic endpoint — surfaces raw Supabase read/write results
and any exception so we can see why caching silently fails. REMOVE after."""
from fastapi import APIRouter
from lib import supabase_client as db

router = APIRouter()


@router.get("/api/debug_supabase")
async def debug_supabase(owner: str = "termux", name: str = "termux-app"):
    out = {}
    out["client_connected"] = db._client is not None
    if not db._client:
        out["note"] = "Supabase not configured -> using in-memory fallback only"
        return out

    # 1) raw read
    try:
        res = (db._client.table("verified_repos").select("*")
               .eq("owner", owner).eq("name", name).execute())
        out["read_ok"] = True
        out["read_data"] = res.data
        out["read_count"] = len(res.data) if res.data else 0
    except Exception as e:
        out["read_ok"] = False
        out["read_error"] = repr(e)

    # 2) raw write (exact shape set_verified builds)
    try:
        row = {"owner": owner, "name": name, "verdict": "Working",
               "summary": "{}", "ai_provider": "debug",
               "verified_at": db._now_iso(), "github_stars_at_time": 1,
               "model": "debug", "reasoning": "debug"}
        r = db._client.table("verified_repos").upsert(row, on_conflict="owner,name").execute()
        out["write_ok"] = True
        out["write_data"] = r.data
    except Exception as e:
        out["write_ok"] = False
        out["write_error"] = repr(e)

    return out
