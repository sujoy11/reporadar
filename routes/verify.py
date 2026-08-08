"""Verify route: cache-first AI repo analysis (Gemini -> Mistral fallback)."""
from fastapi import APIRouter
import os
from lib import github as gh
from lib import ai as ai_lib
from lib import supabase_client as db

router = APIRouter()


@router.get("/api/verify")
async def verify(owner: str = "", name: str = ""):
    if not owner or not name:
        return {"error": "missing_params"}
    full = f"{owner}/{name}"

    # 1) cache
    cached = db.get_verified(owner, name)
    if cached:
        return {"source": "cache", "owner": owner, "name": name,
                "verdict": cached.get("verdict"), "summary": cached.get("summary"),
                "ai_provider": cached.get("ai_provider")}

    # 2) fetch detail
    token = os.environ.get("GITHUB_TOKEN")
    try:
        detail = gh.get_repo_detail(full, token)
    except Exception as e:
        return {"error": "fetch_failed", "message": str(e)}

    # 3) AI
    try:
        text, provider = ai_lib.verify_repo(full, detail)
    except RuntimeError as e:
        return {"error": "ai_unavailable", "message": str(e)}

    # 4) parse structured fields from the AI text
    verdict = "Needs Caution ⚠️"
    maintained = ""
    maturity = ""
    setup = ""
    for line in text.splitlines():
        u = line.upper()
        if "VERDICT" in u:
            verdict = line.split(":", 1)[-1].strip() or verdict
        elif "MAINTAINED" in u:
            maintained = line.split("?", 1)[-1].strip()
        elif "MATURITY" in u:
            maturity = line.split(":", 1)[-1].strip()
        elif "SETUP" in u:
            setup = line.split(":", 1)[-1].strip()
    db.set_verified(owner, name, verdict, text, provider, detail.get("stars", 0))
    return {"source": "live", "owner": owner, "name": name,
            "verdict": verdict, "summary": text, "ai_provider": provider,
            "maintained": maintained, "maturity": maturity, "setup": setup}
