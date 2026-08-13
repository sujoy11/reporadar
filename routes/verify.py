"""Verify route: cache-first AI repo analysis (OpenRouter -> Mistral -> Gemini fallback)."""
from fastapi import APIRouter
import os
import time
import json
from lib import github as gh
from lib import ai as ai_lib
from lib import supabase_client as db

router = APIRouter()


@router.get("/api/verify")
async def verify(owner: str = "", name: str = ""):
    if not owner or not name:
        return {"error": "missing_params"}
    full = f"{owner}/{name}"

    # 1) cache — serve a FRESH verdict (within VERDICT_TTL). An OLD verdict is
    #    treated as expired: fall through to a full re-verification below.
    cached = db.get_verified(owner, name)
    if cached and cached.get("reasoning"):
        age = time.time() - db._parse_ts(cached.get("verified_at"))
        if age < db.VERDICT_TTL:
            return {"source": "cache", "owner": owner, "name": name,
                    "verified_at": db._verified_at_iso(cached.get("verified_at")),
                    "model": cached.get("model") or cached.get("ai_provider") or "AI",
                    "verdict": cached.get("verdict"), "summary": cached.get("summary"),
                    "ai_provider": cached.get("ai_provider"),
                    "maintained": cached.get("maintained"), "maturity": cached.get("maturity"),
                    "community": cached.get("community"), "docs": cached.get("docs"),
                    "setup": cached.get("setup"), "reasoning": cached.get("reasoning")}
    # fall through to fresh verify (no cache, or cached verdict expired)

    # 2) fetch detail
    token = os.environ.get("GITHUB_TOKEN")
    try:
        detail = gh.get_repo_detail(full, token)
    except Exception as e:
        return {"error": "fetch_failed", "message": str(e)}

    # 3) AI
    try:
        fields, model = ai_lib.verify_repo(full, detail)
    except RuntimeError as e:
        return {"error": "ai_unavailable", "message": str(e)}

    verdict = fields.get("verdict") or "Needs Caution"
    summary = json.dumps(fields, ensure_ascii=False)
    db.set_verified(owner, name, verdict, summary, model, detail.get("stars", 0),
                   maintained=fields.get("maintained"), maturity=fields.get("maturity"),
                   community=fields.get("community"), docs=fields.get("docs"),
                   setup=fields.get("setup"), reasoning=fields.get("reasoning"))
    return {"source": "live", "owner": owner, "name": name,
            "verified_at": db._verified_at_iso(None),  # just computed -> now
            "model": model, "summary": summary, "ai_provider": model,
            "verdict": verdict, "maintained": fields.get("maintained"),
            "maturity": fields.get("maturity"), "community": fields.get("community"),
            "docs": fields.get("docs"), "setup": fields.get("setup"),
            "reasoning": fields.get("reasoning")}
