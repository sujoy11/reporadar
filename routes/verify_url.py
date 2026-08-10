"""Direct URL verify: POST /api/verify-url { url } -> full repo detail view.

Reuses lib.github + lib.repo_view to return the SAME shape as /api/repo so the
frontend modal can render it identically. AI verdict is attached from cache if
already verified; otherwise the frontend calls /api/verify separately (or the
route triggers a fresh verify when needed).
"""
from fastapi import APIRouter, Request
import os
import re
from lib import github as gh
from lib import repo_view as view

router = APIRouter()

# github.com/owner/repo  (owner/repo may have trailing path/query — we stop at 2 segments)
_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s?#]+)")


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

    try:
        detail = gh.get_repo_detail(full, token)
        contents = gh.get_repo_contents(full, token)
        data = view.build_view(full, token, name_hint=name, owner_hint=owner,
                               detail=detail, contents=contents)
    except Exception as e:
        return {"error": "fetch_failed", "message": str(e)}

    return data
