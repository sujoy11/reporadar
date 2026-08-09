"""Direct URL verify: POST /api/verify-url { url } -> repo metadata + AI verdict.

Reuses lib.github.get_repo_detail + lib.ai.verify_repo.
Returns the same shape as a repos[] entry used by the frontend modal.
"""
from fastapi import APIRouter, Request
import os
import re
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
    provider = "Gemini"
    if cached and cached.get("reasoning"):
        verdict_raw = cached.get("verdict") or ""
        summary = cached.get("summary") or ""
        provider = cached.get("ai_provider") or "Gemini"
    else:
        try:
            detail = gh.get_repo_detail(full, token)
        except Exception as e:
            return {"error": "fetch_failed", "message": str(e)}
        try:
            text, provider = ai_lib.verify_repo(full, detail)
        except RuntimeError as e:
            return {"error": "ai_unavailable", "message": str(e)}
        import re as _re
        for line in text.splitlines():
            u = line.upper()
            if "VERDICT:" in u or u.startswith("4"):
                verdict_raw = _re.sub(r'^\s*\d+\.\s*', '', line.split(":", 1)[-1]).strip()
                break
        summary = text
        stars = detail.get("stars") or 0
        db.set_verified(owner, name, verdict_raw, text, provider, stars)

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
        "updated": _rel_time(detail.get("pushed_at") or detail.get("updated_at")),
        "url": detail.get("html_url") or f"https://github.com/{full}",
        "verdict": verdict,
        "summary": summary,
        "ai_provider": provider,
    }
