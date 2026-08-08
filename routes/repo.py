"""Repo detail route: full GitHub data for the detail panel."""
from fastapi import APIRouter
import os
from lib import github as gh
from lib import supabase_client as db

router = APIRouter()


@router.get("/api/repo/{owner}/{name}")
async def repo_detail(owner: str = "", name: str = ""):
    if not owner or not name:
        return {"error": "missing_params"}
    full = f"{owner}/{name}"
    token = os.environ.get("GITHUB_TOKEN")
    try:
        detail = gh.get_repo_detail(full, token)
    except Exception as e:
        return {"error": "fetch_failed", "message": str(e)}
    # attach cached AI verdict if present
    cached = db.get_verified(owner, name)
    if cached:
        detail["verdict"] = cached.get("verdict")
        detail["ai_summary"] = cached.get("summary")
    return {"owner": owner, "name": name, "detail": detail}
