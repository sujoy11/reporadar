"""RepoRadar — FastAPI app entrypoint.
Serves static frontend + API routes.
"""
import os
import json
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from routes import search, verify, cron, repo, verify_url, debug_supabase

app = FastAPI(title="RepoRadar")
app.include_router(search.router)
app.include_router(verify.router)
app.include_router(repo.router)
app.include_router(verify_url.router)
app.include_router(debug_supabase.router)  # TEMP diagnostic

BASE = os.path.dirname(os.path.abspath(__file__))


@app.get("/")
async def index():
    # Serve your exact design HTML, inject app.js before </body> (HTML file untouched)
    html = open(os.path.join(BASE, "static", "index.html"), encoding="utf-8").read()
    html = html.replace("</body>", '<script src="/static/app.js"></script>\n</body>')
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html)


@app.get("/repo/{owner}/{name}")
async def repo_page(owner: str, name: str):
    from fastapi.responses import HTMLResponse
    import os as _os
    from lib import github as gh
    from lib import ai as ai_lib
    from lib import supabase_client as db

    full = f"{owner}/{name}"
    token = _os.environ.get("GITHUB_TOKEN")

    # repo detail (stats) — try cache then live
    detail = None
    try:
        detail = gh.get_repo_detail(full, token)
    except Exception:
        detail = {}

    stars = detail.get("stars") or 0
    forks = detail.get("forks") or 0
    pushed = detail.get("pushed_at") or detail.get("updated_at") or ""
    desc = detail.get("description") or "No description provided."

    def fmt(n):
        n = int(n or 0)
        return f"{n/1000:.1f}k" if n >= 1000 else str(n)

    def rel(iso):
        if not iso:
            return "—"
        import time as _t
        d = (_t.time() - _t.mktime(_t.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))) if iso else 0
        if d < 3600: return f"{max(1,int(d/60))}m ago"
        if d < 86400: return f"{int(d/3600)}h ago"
        if d < 2592000: return f"{int(d/86400)}d ago"
        if d < 31536000: return f"{int(d/2592000)}mo ago"
        return f"{int(d/31536000)}y ago"

    # AI verdict — cache-first
    verdict_raw = ""
    summary = ""
    provider = "AI"
    vclass, vlabel = "good", "Working"
    cached = db.get_verified(owner, name)
    if cached and cached.get("reasoning"):
        verdict_raw = cached.get("verdict") or ""
        summary = cached.get("summary") or ""
        provider = cached.get("model") or cached.get("ai_provider") or "AI"
    else:
        try:
            fields, used_model = ai_lib.verify_repo(full, detail)
            verdict_raw = fields.get("verdict") or ""
            summary = json.dumps(fields, ensure_ascii=False)
            provider = used_model
            stars = detail.get("stars") or 0
            db.set_verified(owner, name, verdict_raw, summary, provider, stars,
                           maintained=fields.get("maintained"), maturity=fields.get("maturity"),
                           community=fields.get("community"), docs=fields.get("docs"),
                           setup=fields.get("setup"), reasoning=fields.get("reasoning"),
                           model=provider)
        except Exception:
            verdict_raw = ""
            summary = "AI verdict temporarily unavailable. Check the live site for the full analysis."

    raw = (verdict_raw or "").lower()
    if "outdat" in raw:
        vclass, vlabel = "bad", "Outdated"
    elif "caution" in raw or "warn" in raw:
        vclass, vlabel = "warn", "Needs caution"
    else:
        vclass, vlabel = "good", "Working"

    title = f"{full} — RepoRadar AI verdict"
    description = f"{desc} Stars: {fmt(stars)}. Forks: {fmt(forks)}. AI verdict: {vlabel}. Check if {full} actually works before you build on it."
    canonical = f"https://reporadar-backend.onrender.com/repo/{owner}/{name}"
    rating_value = "5" if vclass == "good" else ("3" if vclass == "warn" else "1")

    tpl = _os.path.join(BASE, "templates", "seo_repo.html")
    with open(tpl, encoding="utf-8") as f:
        tpl_html = f.read()
    repl = {
        "__TITLE__": title,
        "__DESCRIPTION__": description,
        "__CANONICAL__": canonical,
        "__OWNER__": owner + "/",
        "__NAME__": name,
        "__DESC__": desc,
        "__STARS__": fmt(stars),
        "__FORKS__": fmt(forks),
        "__UPDATED__": rel(pushed),
        "__VERDICT_CLASS__": vclass,
        "__VERDICT_LABEL__": vlabel,
        "__RATING_VALUE__": rating_value,
        "__SUMMARY__": summary.replace("&", "&amp;").replace("<", "&lt;"),
        "__AI_PROVIDER__": provider,
        "__REPO_URL__": detail.get("html_url") or f"https://github.com/{full}",
        "__AUTHOR__": owner.rstrip("/"),
    }
    for k, v in repl.items():
        tpl_html = tpl_html.replace(k, str(v))

    return HTMLResponse(tpl_html)



@app.get("/sitemap.xml")
async def sitemap():
    from fastapi.responses import Response
    base = "https://reporadar-backend.onrender.com"
    # curated popular repos to index (extend over time / via cron)
    repos = [
        ("termux", "termux-app"), ("termux", "termux-packages"),
        ("torvalds", "linux"), ("facebook", "react"), ("vuejs", "vue"),
        ("tensorflow", "tensorflow"), ("rust-lang", "rust"), ("django", "django"),
        ("pallets", "flask"), ("expressjs", "express"), ("twbs", "bootstrap"),
        ("redis", "redis"), ("git", "git"), ("npm", "cli"),
        ("nodejs", "node"), ("vercel", "next.js"), ("angular", "angular"),
        ("sveltejs", "svelte"), ("denoland", "deno"), ("microsoft", "vscode"),
        ("python", "cpython"), ("apple", "swift"), ("golang", "go"),
        ("llvm", "llvm-project"), ("keras-team", "keras"), ("pytorch", "pytorch"),
        ("openjdk", "jdk"), ("ruby", "ruby"), ("rails", "rails"),
        ("php", "php-src"), ("laravel", "laravel"), ("symfony", "symfony"),
        ("nginx", "nginx"), ("moby", "moby"), ("kubernetes", "kubernetes"),
        ("hashicorp", "terraform"), ("gradle", "gradle"), ("jetbrains", "kotlin"),
        ("neovim", "neovim"), ("vim", "vim"), ("postgres", "postgres"),
        ("mongodb", "mongo"), ("redis", "redis"), ("elastic", "elasticsearch"),
        ("apache", "kafka"), ("rabbitmq", "rabbitmq-server"), ("graphql", "graphql-js"),
        ("axios", "axios"), ("lodash", "lodash"), ("jquery", "jquery"),
        ("chartjs", "Chart.js"), ("moment", "moment"), ("tailwindlabs", "tailwindcss"),
        ("supabase", "supabase"), ("vercel", "swr"), ("pmndrs", "zustand"),
        ("reduxjs", "redux"), ("vuejs", "vuex"), ("piniajs", "pinia"),
    ]
    urls = [f"  <url><loc>{base}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for o, n in repos:
        urls.append(f"  <url><loc>{base}/repo/{o}/{n}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    from fastapi.responses import PlainTextResponse
    body = "User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: https://reporadar-backend.onrender.com/sitemap.xml\n"
    return PlainTextResponse(body)


app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
