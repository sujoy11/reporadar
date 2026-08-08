"""Search route: cache-first GitHub live search."""
from fastapi import APIRouter, Request
import os
from lib import github as gh
from lib import supabase_client as db

router = APIRouter()


@router.get("/api/search")
async def search(request: Request, q: str = "", per_page: int = 30):
    q = (q or "").strip().lower()
    if not q:
        return {"error": "empty_query", "results": []}

    # 1) cache
    cached = db.get_cached_search(q)
    if cached is not None:
        return {"source": "cache", "query": q, "results": cached}

    # 2) live
    token = os.environ.get("GITHUB_TOKEN")
    try:
        results = gh.search_repositories(q, token, per_page=per_page)
    except RuntimeError as e:
        if "rate_limit" in str(e):
            return {"error": "rate_limit", "message": "Search API busy, try again in a few minutes.",
                    "results": []}
        return {"error": "github_error", "message": str(e), "results": []}

    # filter noise
    results = [r for r in results if not r["archived"] and not r["is_fork"]]
    db.set_cached_search(q, results)

    # fallback: if 0 results, retry with a looser (shorter) query
    if not results:
        words = q.split()
        if len(words) > 2:
            loose = " ".join(words[:2])
            try:
                loose_res = gh.search_repositories(loose, token, per_page=per_page)
                loose_res = [r for r in loose_res if not r["archived"] and not r["is_fork"]]
                if loose_res:
                    db.set_cached_search(q, loose_res)
                    return {"source": "live", "query": q, "results": loose_res,
                            "note": f"No exact match; showing results for '{loose}'"}
            except Exception:
                pass

    return {"source": "live", "query": q, "results": results}
