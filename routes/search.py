"""Search route: cache-first GitHub live search. Supports free-text q and category."""
from fastapi import APIRouter, Request
import os
from lib import github as gh
from lib import supabase_client as db

router = APIRouter()

# Map frontend category chips -> GitHub search queries (free tier, no API key needed)
CATEGORY_QUERIES = {
    "trending": "stars:>5000",
    "termux": "termux",
    "android-rom": "android rom custom in:name,description",
    "ai-ml": "machine-learning OR deep-learning OR llm in:name,description stars:>500",
    "devops": "devops OR kubernetes OR docker in:name,description stars:>500",
    "web-dev": "react OR vue OR nextjs in:name,description stars:>500",
    "mobile-dev": "flutter OR react-native OR android in:name,description stars:>500",
    "security": "security OR pentest OR ctf in:name,description stars:>300",
    "game-dev": "game engine OR gamedev in:name,description stars:>300",
    "data-science": "pandas OR numpy OR data-science in:name,description stars:>500",
    "cli-tools": "cli tool in:name,description stars:>300",
    "automation": "automation OR bot in:name,description stars:>300",
    "backend": "api server in:name,description stars:>500",
    "frontend": "frontend OR ui component in:name,description stars:>500",
    "blockchain": "blockchain OR web3 OR solidity in:name,description stars:>300",
    "iot": "iot OR arduino OR esp32 in:name,description stars:>300",
    "cloud": "aws OR gcp OR cloud in:name,description stars:>500",
    "database": "database OR postgres OR redis in:name,description stars:>300",
    "chrome-ext": "chrome extension in:name,description stars:>100",
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
