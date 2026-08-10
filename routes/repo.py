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
    # normalize fields the frontend modal expects (raw numbers — frontend
    # formats via its own formatCount(), never pre-formatted strings)
    return {
        "owner": owner,
        "name": name,
        "detail": {
            "stars": detail.get("stars"),
            "forks": detail.get("forks"),
            "watchers": detail.get("watchers"),
            "open_issues": detail.get("open_issues"),
            "contributors": detail.get("contributors"),
            "language": detail.get("language") or "Unknown",
            "license": detail.get("license") or "None",
            "archived": detail.get("archived", False),
            "created_at": detail.get("created_at"),
            "pushed_at": detail.get("pushed_at"),
            "default_branch": detail.get("default_branch") or "main",
            "size_kb": detail.get("size_kb"),
            "homepage": detail.get("homepage") or "",
            "html_url": detail.get("html_url"),
            "description": detail.get("description") or "",
            "topics": detail.get("topics", []),
            "readme": (detail.get("readme") or "")[:400],
            "verdict": detail.get("verdict"),
            "ai_summary": detail.get("ai_summary"),
        },
    }
