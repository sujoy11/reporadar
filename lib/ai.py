"""AI verification: Gemini primary, Mistral fallback. Both free tier."""
import os
import urllib.request
import json


PROMPT = """You are analyzing a GitHub repository based ONLY on the data provided.
Do not invent facts. Answer in 5 short parts.

Repository: {full_name}
Description: {description}
README (first part): {readme}
Recent commits: {commits}
Latest release: {latest_release}
Last push: {pushed_at}
Archived: {archived}

Answer (keep each line short, plain text, no markdown):
1. MAINTAINED: Yes/No/Unclear + one short reason
2. MATURITY: Production-ready / Experimental / Early-stage
3. SETUP: Simple / Moderate / Complex
4. VERDICT: Working ✅ / Needs Caution ⚠️ / Outdated ❌
5. REASONING: one concise sentence explaining WHY the verdict is what it is (e.g. "Recent commits + stable releases + active issues = working" or "Last update 2 years ago + no releases = outdated" or "Some activity but no recent release + open critical bugs = caution")."""


def _call_mistral(full_name, data):
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("no_mistral_key")
    prompt = PROMPT.format(
        full_name=full_name,
        description=data.get("description", ""),
        readme=(data.get("readme") or "")[:2000],
        commits="; ".join(f"{c['date'][:10]}: {c['msg']}" for c in data.get("commits", [])[:3]),
        latest_release=data.get("latest_release") or "none",
        pushed_at=data.get("pushed_at") or "unknown",
        archived=data.get("archived"),
    )
    body = json.dumps({
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=30)
    return json.loads(r.read().decode())["choices"][0]["message"]["content"], "mistral"


def _call_gemini(full_name, data):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no_gemini_key")
    prompt = PROMPT.format(
        full_name=full_name,
        description=data.get("description", ""),
        readme=(data.get("readme") or "")[:2000],
        commits="; ".join(f"{c['date'][:10]}: {c['msg']}" for c in data.get("commits", [])[:3]),
        latest_release=data.get("latest_release") or "none",
        pushed_at=data.get("pushed_at") or "unknown",
        archived=data.get("archived"),
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=30)
    txt = json.loads(r.read().decode())["candidates"][0]["content"]["parts"][0]["text"]
    return txt, "gemini"


def verify_repo(full_name, data):
    """Mistral primary (OpenCompare-style), Gemini fallback. Returns (verdict_text, provider)."""
    try:
        return _call_mistral(full_name, data)
    except Exception:
        try:
            return _call_gemini(full_name, data)
        except Exception as e:
            raise RuntimeError(f"ai_unavailable: {e}")
