"""Cron routes: /health, /api/prewarm, /api/keepalive. Protected by CRON_SECRET."""
from fastapi import APIRouter, Request, Header
import os
from lib import github as gh
from lib import supabase_client as db

router = APIRouter()

POPULAR = ["termux", "ai agent", "automation", "web development",
           "fastapi", "react dashboard", "telegram bot", "rag",
           "next.js saas", "custom rom", "pdf tool", "cli tool"]


def _auth(authorization: str = Header(None)):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True  # dev mode: no secret set
    return authorization == f"Bearer {secret}"


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/api/prewarm")
async def prewarm(authorization: str = Header(None)):
    if not _auth(authorization):
        return {"error": "unauthorized"}, 401
    token = os.environ.get("GITHUB_TOKEN")
    done = 0
    for q in POPULAR:
        try:
            if db.get_cached_search(q.lower()) is None:
                res = gh.search_repositories(q, token, per_page=30)
                res = [r for r in res if not r["archived"] and not r["is_fork"]]
                db.set_cached_search(q.lower(), res)
                done += 1
        except Exception:
            continue
    return {"prewarmed": done}


@router.get("/api/keepalive")
async def keepalive(authorization: str = Header(None)):
    if not _auth(authorization):
        return {"error": "unauthorized"}, 401
    ok = db.keepalive()
    return {"keepalive": ok}
