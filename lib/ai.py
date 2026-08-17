"""AI verification: OpenRouter (free gemma-4-26b) primary, Mistral + Gemini fallback.
Returns structured JSON fields, not raw text. Real model slug is returned so the
frontend can show the exact model that produced the verdict.
"""
import os
import urllib.request
import json

OPENROUTER_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
OPENROUTER_MODEL_FALLBACK = "google/gemma-4-26b-a4b-it:free"
MISTRAL_MODEL = "mistral-small-latest"
GEMINI_MODEL = "gemini-2.5-flash"

PROMPT = """You are analyzing a GitHub repository based ONLY on the data provided.
Do not invent facts. Reply with ONLY a single JSON object (no markdown, no code
fences, no commentary) with exactly these keys:

{{
  "maintained": "short phrase: recent commit/push activity (e.g. 'Active — commits within the last week')",
  "maturity": "short phrase: maturity/stability/adoption (e.g. 'Production-ready, widely used')",
  "community": "short phrase: issue/PR responsiveness (e.g. 'Active — issues answered within days')",
  "docs": "short phrase: README/docs quality (e.g. 'Clear README with setup steps')",
  "setup": "Simple / Moderate / Complex",
  "verdict": "Working / Needs Caution / Outdated",
  "reasoning": "one concise sentence explaining WHY the verdict is what it is"
}}

Repository: {full_name}
Description: {description}
README (first part): {readme}
Recent commits: {commits}
Latest release: {latest_release}
Last push: {pushed_at}
Archived: {archived}
"""


def _parse_json(text):
    """Extract a JSON object from an LLM response (handles stray prose/fences)."""
    s = text.strip()
    # strip code fences if any
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1:
        s = s[start:end + 1]
    return json.loads(s)


def _call_openrouter(full_name, data, model=OPENROUTER_MODEL):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no_openrouter_key")
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
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=40)
    content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    return _parse_json(content), model


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
        "model": MISTRAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=30)
    content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    return _parse_json(content), MISTRAL_MODEL


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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=30)
    txt = json.loads(r.read().decode())["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json(txt), GEMINI_MODEL


# ---------------------------------------------------------------------------
# Generic natural-language JSON caller (used by the NL search layer).
# Reuses the SAME provider chain as verify_repo: OpenRouter primary ->
# OpenRouter fallback -> Mistral -> Gemini. Does NOT touch verify_repo.
# ---------------------------------------------------------------------------
def _raw_openrouter(prompt, model=OPENROUTER_MODEL):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no_openrouter_key")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=40)
    content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    return _parse_json(content)


def _raw_mistral(prompt):
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("no_mistral_key")
    body = json.dumps({
        "model": MISTRAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=30)
    content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    return _parse_json(content)


def _raw_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no_gemini_key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=30)
    txt = json.loads(r.read().decode())["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json(txt)


def call_ai_json(prompt):
    """Run a natural-language -> JSON task through the provider chain.
    Returns the parsed dict, or raises RuntimeError if all providers fail."""
    last_err = None
    for fn in (_raw_openrouter, _raw_mistral, _raw_gemini):
        try:
            return fn(prompt)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"ai_unavailable: {last_err}")


def verify_repo(full_name, data):
    """OpenRouter primary (nemotron-omni-30b) -> OpenRouter fallback (gemma-4-26b)
    -> Mistral -> Gemini. Returns (fields_dict, real_model_slug)."""
    last_err = None
    attempts = [
        (_call_openrouter, (OPENROUTER_MODEL,)),
        (_call_openrouter, (OPENROUTER_MODEL_FALLBACK,)),
        (_call_mistral, ()),
        (_call_gemini, ()),
    ]
    for fn, args in attempts:
        try:
            fields, model = fn(full_name, data, *args)
            out = {
                "maintained": str(fields.get("maintained", "")).strip(),
                "maturity": str(fields.get("maturity", "")).strip(),
                "community": str(fields.get("community", "")).strip(),
                "docs": str(fields.get("docs", "")).strip(),
                "setup": str(fields.get("setup", "")).strip(),
                "verdict": str(fields.get("verdict", "")).strip(),
                "reasoning": str(fields.get("reasoning", "")).strip(),
            }
            if not out["reasoning"]:
                raise ValueError("empty reasoning")
            return out, model
        except Exception as e:
            last_err = e
    raise RuntimeError(f"ai_unavailable: {last_err}")
