"""Search route: cache-first GitHub live search. Supports free-text q and category."""
from fastapi import APIRouter, Request
import os
from lib import github as gh
from lib import supabase_client as db

router = APIRouter()

# Map frontend category chips -> GitHub search queries (topic-based, free tier)
CATEGORY_QUERIES = {
    "trending": "stars:>5000",
    "termux": "topic:termux",
    "android-rom": "topic:custom-rom OR topic:android-rom OR topic:android",
    "ai-ml": "topic:machine-learning OR topic:deep-learning OR topic:artificial-intelligence OR topic:neural-network",
    "devops": "topic:devops OR topic:ci-cd OR topic:kubernetes OR topic:docker",
    "web-dev": "topic:web OR topic:web-development OR topic:frontend",
    "mobile-dev": "topic:android OR topic:ios OR topic:mobile OR topic:flutter",
    "security": "topic:security OR topic:cybersecurity OR topic:pentesting",
    "game-dev": "topic:game-development OR topic:game-engine OR topic:gamedev",
    "data-science": "topic:data-science OR topic:data-analysis OR topic:machine-learning",
    "cli-tools": "topic:cli OR topic:command-line OR topic:terminal",
    "automation": "topic:automation OR topic:bot OR topic:script",
    "backend": "topic:backend OR topic:api OR topic:server",
    "frontend": "topic:frontend OR topic:ui OR topic:react OR topic:vue",
    "blockchain": "topic:blockchain OR topic:web3 OR topic:ethereum OR topic:solidity",
    "iot": "topic:iot OR topic:arduino OR topic:esp32 OR topic:raspberry-pi",
    "cloud": "topic:cloud OR topic:aws OR topic:azure OR topic:gcp",
    "database": "topic:database OR topic:sql OR topic:postgresql OR topic:redis",
    "chrome-ext": "topic:chrome-extension OR topic:browser-extension OR topic:firefox-extension",
    "open-source": "stars:>1000",
}


@router.get("/api/search")
async def search(request: Request, q: str = "", category: str = "", per_page: int = 30):
    q = (q or "").strip().lower()
    category = (category or "").strip().lower()

    # category mode
    if category and category in CATEGORY_QUERIES:
        cq = CATEGORY_QUERIES[category]
        cached = db.get_cached_search("cat:" + category)
        if cached is not None:
            return {"source": "cache", "query": cq, "category": category, "results": cached}
        token = os.environ.get("GITHUB_TOKEN")
        try:
            results = gh.search_repositories(cq, token, per_page=per_page)
        except RuntimeError as e:
            if "rate_limit" in str(e):
                return {"error": "rate_limit", "message": "Search API busy, try again in a few minutes.", "results": []}
            return {"error": "github_error", "message": str(e), "results": []}
        results = [r for r in results if not r["archived"] and not r["is_fork"]]
        db.set_cached_search("cat:" + category, results)
        return {"source": "live", "query": cq, "category": category, "results": results}

    # text query mode
    if not q:
        return {"error": "empty_query", "results": []}

    cached = db.get_cached_search(q)
    if cached is not None:
        return {"source": "cache", "query": q, "results": cached}

    token = os.environ.get("GITHUB_TOKEN")
    try:
        results = gh.search_repositories(q, token, per_page=per_page)
    except RuntimeError as e:
        if "rate_limit" in str(e):
            return {"error": "rate_limit", "message": "Search API busy, try again in a few minutes.",
                    "results": []}
        return {"error": "github_error", "message": str(e), "results": []}

    results = [r for r in results if not r["archived"] and not r["is_fork"]]
    db.set_cached_search(q, results)

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
