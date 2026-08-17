"""Cron routes: /health, /api/prewarm, /api/keepalive. Protected by CRON_SECRET."""
from fastapi import APIRouter, Request, Header
import os
import threading
from lib import github as gh
from lib import supabase_client as db
from routes.search import CATEGORY_QUERIES

router = APIRouter()

_prewarm_lock = threading.Lock()
_prewarm_running = False


def _auth(authorization: str = Header(None)):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True  # dev mode: no secret set
    return authorization == f"Bearer {secret}"


def _do_prewarm():
    """Iterate over CATEGORY_QUERIES and fill the cache using the exact keys
    the frontend requests ("cat:" + key). Runs in a background thread so
    the /api/prewarm endpoint returns immediately (critical for free-tier
    cold starts where the cron curl would otherwise time out)."""
    global _prewarm_running
    token = os.environ.get("GITHUB_TOKEN")
    try:
        for key, query in CATEGORY_QUERIES.items():
            try:
                if db.get_cached_search("cat:" + key) is None:
                    res = gh.search_repositories(query, token, per_page=30)
                    res = [r for r in res if not r["archived"] and not r["is_fork"]]
                    db.set_cached_search("cat:" + key, res)
            except Exception:
                continue
    finally:
        with _prewarm_lock:
            _prewarm_running = False


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/api/prewarm")
async def prewarm(authorization: str = Header(None)):
    if not _auth(authorization):
        return {"error": "unauthorized"}, 401
    global _prewarm_running
    with _prewarm_lock:
        if _prewarm_running:
            return {"prewarming": True, "note": "already running"}
        _prewarm_running = True
    t = threading.Thread(target=_do_prewarm, daemon=True)
    t.start()
    return {"prewarming": True}


@router.get("/api/keepalive")
async def keepalive(authorization: str = Header(None)):
    if not _auth(authorization):
        return {"error": "unauthorized"}, 401
    ok = db.keepalive()
    return {"keepalive": ok}
