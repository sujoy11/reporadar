"""GitHub API helpers: search (rate-limited) + core repo detail fetch."""
import urllib.request
import urllib.error
import urllib.parse
import json
import os
import re
from lib.markdown import markdown_to_html


def _headers(token, accept="application/vnd.github+json"):
    h = {"User-Agent": "RepoRadar", "Accept": accept}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def search_repositories(query, token, per_page=30):
    """Live GitHub Search API. Returns list of normalized repo dicts or raises.

    Query is made intent-aware:
    - Generic intent verbs (install/setup/how-to/guide/download/use...) are
      dropped — they hurt relevance because GitHub then matches any repo
      containing the word instead of the actual topic.
    - Remaining topic terms are scoped to name/description so results are
      about the topic, surfacing the real project (e.g. "Hermes Install"
      -> search "hermes" -> NousResearch/hermes-agent at top).
    """
    STOP = {"install", "setup", "how", "to", "guide", "tutorial", "download",
            "get", "use", "using", "for", "the", "a", "an", "best", "top",
            "app", "tool", "github", "reddit", "vs", "alternative", "free",
            "in", "on", "of", "me", "my", "you", "your", "with", "and", "or",
            "ios", "android", "windows", "macos", "linux", "web", "api", "ui"}
    # Server-side sanitization: a pasted search-engine / share URL can carry
    # tracking params (e.g. Google's &ved=...) that would otherwise flow
    # straight into the GitHub query and corrupt the result. Strip anything
    # from the first '&' or '?' — valid GitHub qualifiers never use those.
    query = query.split("&")[0].split("?")[0].strip()
    words = [w for w in query.lower().split() if w not in STOP]
    if not words:
        words = query.lower().split()[:3]
    # Build the GitHub query. Appending 'in:name,description' only makes sense
    # for plain free-text topic words; if the query already contains a GitHub
    # qualifier (stars:, topic:, language:, user:, org:, ...), leave it intact
    # — otherwise 'stars:>5000 in:name,description' matches almost nothing and
    # the trending category returns only a handful of repos.
    if any(":" in w for w in words):
        q = " ".join(words)
    else:
        q = " ".join(words) + " in:name,description"
    url = (f"https://api.github.com/search/repositories?q={urllib.parse.quote_plus(q)}"
           f"&sort=stars&order=desc&per_page={per_page}")
    req = urllib.request.Request(url, headers=_headers(token))
    try:
        r = urllib.request.urlopen(req, timeout=25)
        data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError("rate_limit_search")
        raise RuntimeError(f"github_search_{e.code}")
    items = []
    for it in data.get("items", []):
        items.append({
            "id": it["id"],
            "name": it["name"],
            "owner": it["owner"]["login"],
            "full_name": it["full_name"],
            "description": (it.get("description") or "")[:160],
            "url": it["html_url"],
            "stars": it["stargazers_count"],
            "forks": it["forks_count"],
            "language": it.get("language") or "Unknown",
            "topics": it.get("topics", []),
            "license": (it.get("license") or {}).get("spdx_id") or "None",
            "updated_at": it.get("pushed_at") or it.get("updated_at"),
            "created_at": it.get("created_at"),
            "archived": it.get("archived", False),
            "is_fork": it.get("fork", False),
        })
    return items


def get_repo_detail(full_name, token):
    """Core API: full repo + readme + last 5 commits + releases. 5000/hr limit."""
    base = f"https://api.github.com/repos/{full_name}"
    out = {"full_name": full_name}

    def get(path, accept="application/vnd.github+json"):
        req = urllib.request.Request(base + path, headers=_headers(token, accept))
        return json.loads(urllib.request.urlopen(req, timeout=20).read().decode())

    try:
        repo = get("")
        out.update({
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "watchers": repo.get("subscribers_count"),
            "open_issues": repo.get("open_issues_count"),
            "language": repo.get("language") or "Unknown",
            "license": (repo.get("license") or {}).get("spdx_id"),
            "html_url": repo.get("html_url"),
            "created_at": repo.get("created_at"),
            "pushed_at": repo.get("pushed_at"),
            "default_branch": repo.get("default_branch"),
            "size_kb": repo.get("size"),
            "homepage": repo.get("homepage") or "",
            "archived": repo.get("archived", False),
            "topics": repo.get("topics", []) or [],
            "description": repo.get("description") or "",
        })
    except Exception:
        pass

    # Contributors count (last page link header -> total)
    try:
        req = urllib.request.Request(base + "/contributors?per_page=1&anon=false",
                                     headers=_headers(token))
        resp = urllib.request.urlopen(req, timeout=20)
        link = resp.headers.get("Link") or ""
        m = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
        out["contributors"] = int(m.group(1)) if m else len(json.loads(resp.read().decode()))
    except Exception:
        out["contributors"] = None

    # README (fetched as raw text, not JSON — the raw accept returns markdown,
    # not a JSON envelope). Convert to sanitized HTML.
    try:
        req = urllib.request.Request(base + "/readme",
                                     headers=_headers(token, "application/vnd.github.raw+json"))
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        out["readme"] = raw[:2000]
        out["readme_html"] = markdown_to_html(raw[:4000])
    except Exception:
        out["readme"] = ""
        out["readme_html"] = ""

    # Last 5 commits
    try:
        commits = get("/commits?per_page=5")
        out["commits"] = [{"date": c["commit"]["committer"]["date"],
                           "msg": c["commit"]["message"][:120]}
                          for c in commits]
    except Exception:
        out["commits"] = []

    # Releases
    try:
        rel = get("/releases?per_page=1")
        out["latest_release"] = rel[0]["published_at"] if rel else None
    except Exception:
        out["latest_release"] = None

    return out


def get_repo_contents(full_name, token, path=""):
    """Return top-level file/folder listing from the GitHub contents API.

    Falls back to [] on any error. Each entry: {name, type ('dir'|'file'),
    size, html_url}. Sorted dirs-first then alpha.
    """
    try:
        url = f"https://api.github.com/repos/{full_name}/contents/{path}"
        req = urllib.request.Request(url, headers=_headers(token))
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    items = []
    for it in data:
        t = it.get("type")
        items.append({
            "name": it.get("name", ""),
            "type": "dir" if t == "dir" else "file",
            "size": it.get("size", 0),
            "html_url": it.get("html_url", ""),
            "path": it.get("path", ""),
        })
    # dirs first, then alphabetical
    items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
    return items[:30]
