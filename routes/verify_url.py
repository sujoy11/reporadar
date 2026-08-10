"""Direct URL verify: POST /api/verify-url { url } -> repo metadata + AI verdict.

Reuses lib.github.get_repo_detail + lib.ai.verify_repo.
Returns the same shape as a repos[] entry used by the frontend modal.
"""
from fastapi import APIRouter, Request
import os
import re
import json
import urllib.parse
from lib import github as gh
from lib import ai as ai_lib
from lib import supabase_client as db

router = APIRouter()

# github.com/owner/repo  (owner/repo may have trailing path/query — we stop at 2 segments)
_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s?#]+)")


def _fmt_stars(n):
    n = int(n or 0)
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def _rel_time(iso):
    if not iso:
        return "—"
    try:
        import time
        d = time.time() - time.mktime(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return "—"
    if d < 3600:
        return f"{max(1, int(d/60))}m ago"
    if d < 86400:
        return f"{int(d/3600)}h ago"
    if d < 2592000:
        return f"{int(d/86400)}d ago"
    if d < 31536000:
        return f"{int(d/2592000)}mo ago"
    return f"{int(d/31536000)}y ago"


@router.post("/api/verify-url")
async def verify_url(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"error": "bad_json"}

    url = (body.get("url") or "").strip()
    if not url:
        return {"error": "empty_url"}

    m = _URL_RE.search(url)
    if not m:
        return {"error": "invalid_url", "message": "Please paste a valid github.com/owner/repo link."}

    owner = m.group(1)
    name = m.group(2)
    full = f"{owner}/{name}"
    token = os.environ.get("GITHUB_TOKEN")

    # cached AI verdict first
    cached = db.get_verified(owner, name)
    verdict_raw = ""
    summary = ""
    provider = "AI"
    maintained = maturity = community = docs = setup = reasoning = ""
    model = "AI"
    if cached and cached.get("reasoning"):
        verdict_raw = cached.get("verdict") or ""
        summary = cached.get("summary") or ""
        provider = cached.get("ai_provider") or "AI"
        model = cached.get("model") or provider
        maintained = cached.get("maintained") or ""
        maturity = cached.get("maturity") or ""
        community = cached.get("community") or ""
        docs = cached.get("docs") or ""
        setup = cached.get("setup") or ""
        reasoning = cached.get("reasoning") or ""
    else:
        try:
            detail = gh.get_repo_detail(full, token)
        except Exception as e:
            return {"error": "fetch_failed", "message": str(e)}
        try:
            fields, used_model = ai_lib.verify_repo(full, detail)
        except RuntimeError as e:
            return {"error": "ai_unavailable", "message": str(e)}
        verdict_raw = fields.get("verdict") or ""
        summary = json.dumps(fields, ensure_ascii=False)
        provider = used_model
        model = used_model
        maintained = fields.get("maintained") or ""
        maturity = fields.get("maturity") or ""
        community = fields.get("community") or ""
        docs = fields.get("docs") or ""
        setup = fields.get("setup") or ""
        reasoning = fields.get("reasoning") or ""
        stars = detail.get("stars") or 0
        db.set_verified(owner, name, verdict_raw, summary, model, stars,
                       maintained=maintained, maturity=maturity, community=community,
                       docs=docs, setup=setup, reasoning=reasoning, model=model)


    raw = verdict_raw.lower()
    if "outdat" in raw:
        verdict = "bad"
    elif "caution" in raw or "warn" in raw:
        verdict = "warn"
    else:
        verdict = "good"

    # refetch detail for stats (may already have it above; do a light call)
    try:
        detail = gh.get_repo_detail(full, token)
    except Exception:
        detail = {}

    return {
        "owner": owner + "/",
        "name": name,
        "desc": detail.get("description") or "No description provided.",
        "stars": _fmt_stars(detail.get("stars") or 0),
        "forks": _fmt_stars(detail.get("forks") or 0),
        "watchers": detail.get("watchers"),
        "open_issues": detail.get("open_issues"),
        "contributors": detail.get("contributors"),
        "language": detail.get("language") or "Unknown",
        "license": detail.get("license") or "None",
        "archived": detail.get("archived", False),
        "created_at": detail.get("created_at"),
        "default_branch": detail.get("default_branch") or "main",
        "size_kb": detail.get("size_kb"),
        "homepage": detail.get("homepage") or "",
        "topics": detail.get("topics", []),
        "readme": (detail.get("readme") or "")[:400],
        "updated": _rel_time(detail.get("pushed_at") or detail.get("updated_at")),
        "url": detail.get("html_url") or f"https://github.com/{full}",
        "verdict": verdict,
        "summary": summary,
        "ai_provider": provider,
        "maintained": maintained,
        "maturity": maturity,
        "community": community,
        "docs": docs,
        "setup": setup,
        "reasoning": reasoning,
        "model": model,
    }
