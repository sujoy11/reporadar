"""Search route: cache-first GitHub live search. Supports free-text q and category.

Adds a natural-language search layer (STEP 1-6) that sits IN FRONT of the
existing keyword search. It NEVER touches lib/github.py's core search
function, the category chip system, or any frontend CSS/animations.
Plain-keyword queries (e.g. "termux") use the original flow unchanged.
"""
from fastapi import APIRouter, Request
import os
import json
from lib import github as gh
from lib import supabase_client as db
from lib import ai as ai_lib

router = APIRouter()

# Map frontend category chips -> GitHub search queries (topic-based, free tier)
CATEGORY_QUERIES = {
    "trending": "stars:>5000",
    "termux": "topic:termux",
    "rom": "topic:custom-rom OR topic:android-rom OR topic:android",
    "ai-ml": "topic:machine-learning OR topic:deep-learning OR topic:artificial-intelligence OR topic:neural-network",
    "devops": "topic:devops OR topic:ci-cd OR topic:kubernetes OR topic:docker",
    "automation": "topic:automation OR topic:bot OR topic:script",
    "webdev": "topic:web OR topic:web-development OR topic:frontend OR topic:javascript",
    "mobile": "topic:android OR topic:ios OR topic:mobile OR topic:flutter",
    "saas": "topic:saas OR topic:starter-kit OR topic:boilerplate",
    "cybersecurity": "topic:security OR topic:cybersecurity OR topic:pentesting",
    "data-science": "topic:data-science OR topic:data-analysis OR topic:machine-learning",
    "blockchain": "topic:blockchain OR topic:web3 OR topic:ethereum OR topic:solidity",
    "cli": "topic:cli OR topic:command-line OR topic:terminal",
    "self-hosted": "topic:self-hosted OR topic:selfhosted OR topic:homelab",
    "chrome-ext": "topic:chrome-extension OR topic:browser-extension OR topic:firefox-extension",
    "telegram-bots": "topic:telegram-bot OR topic:telegram OR topic:bot",
}

# ---------------------------------------------------------------------------
# NATURAL-LANGUAGE SEARCH LAYER
# ---------------------------------------------------------------------------
NL_TRIGGERS = {"find", "with", "for", "that", "like", "me", "a", "an", "the",
               "something", "need", "want"}


def is_natural_language(q):
    """STEP 1: NL if >3 words AND contains at least one trigger word."""
    words = q.split()
    if len(words) <= 3:
        return False
    return any(w in NL_TRIGGERS for w in words)


def _translate_nl(raw_query):
    """STEP 2: AI -> 2-3 GitHub qualifier variants. Returns list[str] or None."""
    prompt = (
        "Convert this natural-language GitHub repo search request into 2-3 valid "
        "GitHub search qualifier strings (language:, topic:, stars:>N, etc): one "
        "precise/narrow version and one or two broader versions (drop a "
        "less-critical qualifier in each broader version). Before producing "
        "qualifiers, silently expand common developer-language substitutions "
        "(e.g. 'login system' -> authentication/oauth, 'expense tracker' -> "
        "budget/finance, 'chatbot' -> conversational-ai/llm) -- do not explain "
        "this, just apply it. Return ONLY a JSON object: "
        "{\"variants\": [\"query1\", \"query2\", ...]}. Request: " + raw_query
    )
    try:
        out = ai_lib.call_ai_json(prompt)
        variants = out.get("variants") or []
        # normalize to plain strings, max 3
        cleaned = [str(v).strip() for v in variants if str(v).strip()][:3]
        return cleaned or None
    except Exception:
        return None


def _rerank_nl(raw_query, repos):
    """STEP 5: AI relevance-first rerank. Returns (ordered_repos, tag_map)."""
    tag_map = {}
    if not repos:
        return repos, tag_map
    top = repos[:25]
    items = []
    for r in top:
        items.append({
            "full_name": r.get("full_name", ""),
            "description": (r.get("description") or "")[:200],
            "language": r.get("language") or "Unknown",
            "stars": r.get("stars") or 0,
        })
    payload = {"query": raw_query, "repos": items}
    prompt = (
        "Rank these repositories by how well they actually match what the user "
        "is looking for, based on their description and purpose -- NOT by star "
        "count. A smaller, less popular repo that precisely matches the request "
        "should rank ABOVE a more popular repo that only superficially matches. "
        "Star count should only break ties between two repos that are equally "
        "relevant. Return ONLY a JSON object: "
        "{\"ranked\": [{\"full_name\": \"...\", \"tag\": \"exact\"|\"close\"|\"loose\"}, ...]}"
        "\n\nUser request: " + raw_query +
        "\n\nRepositories:\n" + json.dumps(payload)
    )
    try:
        out = ai_lib.call_ai_json(prompt)
        ranked = out.get("ranked") or []
        order = []
        for e in ranked:
            fn = e.get("full_name", "")
            tag_map[fn] = e.get("tag", "loose")
            order.append(fn)
        # results the AI didn't rank -> append in original star order (tiebreak)
        ranked_set = set(order)
        for r in repos:
            if r.get("full_name") not in ranked_set:
                order.append(r.get("full_name"))
        by_name = {r.get("full_name"): r for r in repos}
        ordered = [by_name[fn] for fn in order if fn in by_name]
        # any leftovers (safety)
        seen_names = {r.get("full_name") for r in ordered}
        ordered += [r for r in repos if r.get("full_name") not in seen_names]
        return ordered, tag_map
    except Exception:
        # fallback: star-sort of merged results, never block
        return sorted(repos, key=lambda r: r.get("stars", 0), reverse=True), tag_map


def _nl_search(raw_query, token, per_page):
    """Full NL pipeline (STEPS 2-6). Returns dict ready for the route response."""
    norm = raw_query.lower().strip()
    variants, cached_ranked = db.get_nl_cache(norm)

    if variants is None:
        variants = _translate_nl(norm)
        if variants is None:
            # STEP 3: AI failed -> treat as plain keyword (current default)
            return None
        db.set_nl_cache(norm, variants)  # cache translation

    # STEP 4: multi-query retrieval, merge + dedupe by full_name
    merged = {}
    for v in variants[:3]:
        cached = db.get_cached_search("nl:" + v)
        if cached is not None:
            items = cached
        else:
            try:
                items = gh.search_repositories(v, token, per_page=per_page)
            except Exception:
                items = []
            if items:
                db.set_cached_search("nl:" + v, items)
        for it in items:
            if it["full_name"] not in merged:
                merged[it["full_name"]] = it
    results = list(merged.values())
    if not results:
        return None  # nothing found -> caller falls back to plain keyword

    # STEP 5: rerank (cached if available)
    if cached_ranked is None:
        results, tag_map = _rerank_nl(norm, results)
        db.set_nl_cache(norm, variants, ranked_order=_tagmap_to_ranked(tag_map, results))
    else:
        # rebuild order from cached ranked_order
        results, tag_map = _apply_cached_ranked(cached_ranked, results)

    # STEP 6: Hidden Gem badge — "exact" tagged + below median stars
    stars = [r.get("stars", 0) or 0 for r in results]
    median = sorted(stars)[len(stars) // 2] if stars else 0
    for r in results:
        fn = r.get("full_name")
        tag = tag_map.get(fn)
        if tag == "exact" and (r.get("stars", 0) or 0) < median:
            r["is_gem"] = True
            r["gem_tag"] = tag
        else:
            r["is_gem"] = False

    return {"source": "nl", "query": norm, "variants": variants,
            "category": "", "results": results}


def _tagmap_to_ranked(tag_map, results):
    return [{"full_name": r.get("full_name"),
             "tag": tag_map.get(r.get("full_name"), "loose")} for r in results]


def _apply_cached_ranked(cached_ranked, results):
    order = [e.get("full_name") for e in (cached_ranked or [])]
    tag_map = {e.get("full_name"): e.get("tag", "loose") for e in (cached_ranked or [])}
    by_name = {r.get("full_name"): r for r in results}
    ordered = [by_name[fn] for fn in order if fn in by_name]
    seen_names = {r.get("full_name") for r in ordered}
    ordered += [r for r in results if r.get("full_name") not in seen_names]
    return ordered, tag_map


@router.get("/api/search")
async def search(request: Request, q: str = "", category: str = "", per_page: int = 30):
    q = (q or "").strip().lower()
    category = (category or "").strip().lower()

    # category mode -- UNCHANGED (no NL layer)
    if category and category in CATEGORY_QUERIES:
        cq = CATEGORY_QUERIES[category]
        cached = db.get_cached_search("cat:" + category)
        if cached is not None:
            return {"source": "cache", "query": cq, "category": category, "results": cached}
        token = os.environ.get("GITHUB_TOKEN")
        try:
            results = gh.search_repositories(cq, token, per_page=per_page)
        except Exception as e:
            if "rate_limit" in str(e):
                return {"error": "rate_limit", "message": "Search API busy, try again in a few minutes.", "results": []}
            return {"error": "github_error", "message": str(e), "results": []}
        results = [r for r in results if not r["archived"] and not r["is_fork"]]
        db.set_cached_search("cat:" + category, results)
        return {"source": "live", "query": cq, "category": category, "results": results}

    # text query mode
    if not q:
        return {"error": "empty_query", "results": []}

    # ---- NL SEARCH LAYER (only for natural-language queries) ----
    if is_natural_language(q):
        token = os.environ.get("GITHUB_TOKEN")
        nl = _nl_search(q, token, per_page)
        if nl is not None:
            return nl
        # if NL layer bailed (AI fail / no results), fall through to plain keyword

    # ---- PLAIN KEYWORD SEARCH (original behavior, unchanged) ----
    cached = db.get_cached_search(q)
    if cached is not None:
        return {"source": "cache", "query": q, "results": cached}

    token = os.environ.get("GITHUB_TOKEN")
    try:
        results = gh.search_repositories(q, token, per_page=per_page)
    except Exception as e:
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
