"""RepoRadar — FastAPI app entrypoint.
Serves static frontend + API routes.
"""
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from routes import search, verify, cron, repo

app = FastAPI(title="RepoRadar")
app.include_router(search.router)
app.include_router(verify.router)
app.include_router(repo.router)

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
    html = open(os.path.join(BASE, "static", "index.html"), encoding="utf-8").read()
    html = html.replace("</body>", '<script src="/static/app.js"></script>\n</body>')
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
