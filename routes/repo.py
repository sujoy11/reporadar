"""Repo detail route: full GitHub data for the detail panel."""
from fastapi import APIRouter
import os
from lib import github as gh
from lib import repo_view as view

router = APIRouter()


@router.get("/api/repo/{owner}/{name}")
async def repo_detail(owner: str = "", name: str = ""):
    if not owner or not name:
        return {"error": "missing_params"}
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
