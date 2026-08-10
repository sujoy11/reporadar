"""Build the unified repo detail view returned by /api/repo and /api/verify-url.

Centralizes: raw stats -> formatted strings + relative times, contents listing,
sanitized README html, and cached AI verdict attachment. Both routes import this
so the modal always gets the same shape.
"""
import os
import time
from lib import github as gh
from lib import supabase_client as db


def _fmt_count(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def _fmt_size(kb):
    kb = int(kb or 0)
    if kb >= 1_048_576:
        return f"{kb / 1_048_576:.1f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


def _rel_time(iso):
    if not iso:
        return "—"
    try:
        d = time.time() - time.mktime(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return "—"
    if d < 0:
        return "just now"
    if d < 3600:
        return f"{max(1, int(d / 60))}m ago"
    if d < 86400:
        return f"{int(d / 3600)}h ago"
    if d < 2592000:
        return f"{int(d / 86400)}d ago"
    if d < 31536000:
        return f"{int(d / 2592000)}mo ago"
    return f"{int(d / 31536000)}y ago"


def build_view(full, token, name_hint=None, owner_hint=None, detail=None, contents=None):
    """Return the full detail view dict. Pass pre-fetched detail/contents to
    avoid duplicate network calls (used by verify_url which already fetched).
    """
    if detail is None:
        try:
            detail = gh.get_repo_detail(full, token)
        except Exception:
            detail = {}

    owner = owner_hint or (detail.get("full_name") or full).split("/")[0]
    name = name_hint or full.split("/")[-1]

    if contents is None:
        contents = gh.get_repo_contents(full, token)

    # attach cached AI verdict if present
    cached = db.get_verified(owner, name)
    verdict = None
    ai_fields = None
    if cached:
        verdict = cached.get("verdict")
        ai_fields = {
            "model": cached.get("model") or cached.get("ai_provider") or "AI",
            "maintained": cached.get("maintained"),
            "maturity": cached.get("maturity"),
            "community": cached.get("community"),
            "docs": cached.get("docs"),
            "setup": cached.get("setup"),
            "reasoning": cached.get("reasoning"),
        }

    return {
        "owner": owner + "/",
        "name": name,
        "url": detail.get("html_url") or f"https://github.com/{full}",
        "desc": detail.get("description") or "No description provided.",
        "category": detail.get("category") or "",
        # formatted stat strings (frontend shows them verbatim)
        "stars": _fmt_count(detail.get("stars")),
        "forks": _fmt_count(detail.get("forks")),
        "watchers": _fmt_count(detail.get("watchers")),
        "open_issues": _fmt_count(detail.get("open_issues")),
        "contributors": _fmt_count(detail.get("contributors")),
        "updated": _rel_time(detail.get("pushed_at") or detail.get("updated_at")),
        "created": (detail.get("created_at") or "")[:10],
        # raw extras for the meta list
        "language": detail.get("language") or "Unknown",
        "license": detail.get("license") or "None",
        "archived": detail.get("archived", False),
        "default_branch": detail.get("default_branch") or "main",
        "size": _fmt_size(detail.get("size_kb")),
        "homepage": detail.get("homepage") or "",
        "topics": detail.get("topics", []),
        "readme_html": detail.get("readme_html") or "",
        "files": [
            {
                "name": c["name"] + ("/" if c["type"] == "dir" else ""),
                "dir": c["type"] == "dir",
                "size": c["size"],
            }
            for c in contents
        ],
        # AI verdict (may be None until runVerify is called)
        "verdict": verdict,
        "ai": ai_fields,
    }
