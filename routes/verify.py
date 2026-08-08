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

    # 1) cache — but if cached entry has no reasoning (old format), re-verify
    cached = db.get_verified(owner, name)
    if cached and cached.get("reasoning"):
        return {"source": "cache", "owner": owner, "name": name,
                "verdict": cached.get("verdict"), "summary": cached.get("summary"),
                "ai_provider": cached.get("ai_provider"),
                "maintained": cached.get("maintained"), "maturity": cached.get("maturity"),
                "setup": cached.get("setup"), "reasoning": cached.get("reasoning")}
    # fall through to fresh verify if no valid cache

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

    # 4) parse structured fields from the AI text (match numbered lines 1-5)
    import re as _re
    verdict = "Needs Caution ⚠️"
    maintained = ""
    maturity = ""
    setup = ""
    reasoning = ""
    def clean(s):
        s = _re.sub(r'^\s*\d+\.\s*', '', s)         # strip "1. "
        s = _re.sub(r'\*\*', '', s)                  # strip bold
        s = _re.sub(r'^(MAINTAINED|MATURITY|SETUP|REASONING)\s*:\s*', '', s, flags=_re.I)  # strip label
        return s.strip()
    for line in text.splitlines():
        u = line.upper()
        if u.startswith("1") and "MAINTAINED:" in u:
            maintained = clean(line.split(":", 1)[-1])
        elif u.startswith("2") and "MATURITY:" in u:
            maturity = clean(line.split(":", 1)[-1])
        elif u.startswith("3") and "SETUP:" in u:
            setup = clean(line.split(":", 1)[-1])
        elif u.startswith("5") and "REASONING:" in u:
            reasoning = clean(line.split(":", 1)[-1])
        elif u.startswith("4") or "VERDICT:" in u:
            verdict = clean(line.split(":", 1)[-1]) or verdict
    db.set_verified(owner, name, verdict, text, provider, detail.get("stars", 0))
    return {"source": "live", "owner": owner, "name": name,
            "verdict": verdict, "summary": text, "ai_provider": provider,
            "maintained": maintained, "maturity": maturity, "setup": setup,
            "reasoning": reasoning}
