# RepoRadar Full Audit & Fix Spec

Repo: github.com/sujoy11/reporadar (FastAPI + static HTML/JS frontend, deployed to Render free tier at https://reporadar-backend.onrender.com)

You are Claude Opus 4.6. The Hermes agent has already read the entire codebase and confirmed these root causes by live testing. Your job: IMPLEMENT the fixes below in /home/ubuntu/reporadar, then report what you changed. Do NOT push or deploy — Hermes will do that after reviewing your diff. Make minimal, surgical changes; do not rewrite working code.

IMPORTANT ENVIRONMENT NOTES:
- The AI provider chain (`lib/ai.py`) depends on env keys OPENROUTER_API_KEY / MISTRAL_API_KEY / GEMINI_API_KEY. On the live server these are likely unset, so OpenRouter/Mistral/Gemini calls raise `RuntimeError("ai_unavailable")` quickly. Account for this in UX.
- Supabase is configured on the live server (the `verified_repos` table only has columns: id, owner, name, verdict, summary, ai_provider, verified_at, github_stars_at_time). It does NOT have maintained/maturity/community/docs/setup/reasoning/model columns. So `db.get_verified()` returns a row whose those fields are all None even when an AI verdict was computed. THIS IS THE ROOT CAUSE of the " — " verdict fields bug.
- The live robots.txt currently returns `Disallow: /` (BLOCKING all crawlers) — a confirmed regression from the intended `Allow: /`. Fix in code.

============================================================
CONFIRMED BUGS & FIXES
============================================================

## BUG 1 — AI verdict fields show " — " on repo detail page (CRITICAL, root cause found)
Root cause: `lib/supabase_client.py::set_verified()` and `get_verified()` already handle the extra columns (maintained/maturity/community/docs/setup/reasoning/model are passed and read), BUT the live `verified_repos` Supabase table was created from `supabase_schema.sql` which only defines the 8 base columns. So `db.set_verified(...)` writes those extra fields only to the in-memory `_MEM_VERIFIED` fallback, NOT to Supabase. `db.get_verified()` then reads from Supabase (when _client is set) and returns a row with all AI sub-fields = None. Frontend `populateDetail`/`runVerify` therefore always show " — " for Maintained/Maturity/Community/Docs/Setup (unless served from the in-memory cache, which is empty after a cold start).

Two-part fix:
(a) Make the AI verdict persist & read correctly. The cleanest fix that doesn't require a Supabase migration (which we can't run from here): store the structured verdict fields INSIDE the existing `summary` TEXT column as JSON when present, AND on read, if the dedicated columns are None but `summary` parses to a dict containing the fields, use those. Concretely:
   - In `lib/supabase_client.py::set_verified()`: when building the row, if `reasoning`/`maintained`/etc. are provided, ensure `summary` (if it's a JSON string holding the dict) is what gets stored (it already stores summary). More robust: ALSO store the full structured dict into `summary` as JSON for both client and memory paths. Keep current behavior.
   - In `db.get_verified()`: after fetching a Supabase row, if `row.get("maintained") is None` (etc.) but `row.get("summary")` looks like JSON containing a "maintained" key, parse it and fill the missing fields (maintained, maturity, community, docs, setup, reasoning, model). Also fill `model` from the parsed dict if missing. This makes cached verdicts render correctly.
   - Do the same fallback in `lib/repo_view.py::build_view()` is not needed if `get_verified` returns a normalized row — keep logic in one place (supabase_client).
   - In the in-memory path `_MEM_VERIFIED.get(key)`, the row already contains the fields, so it's fine.

(b) Loading state (already partially handled): the detail modal `blankDetailFields()` + `aiLoading` show skeletons, good. But the FIRST time a user opens a repo and clicks "Get AI details", if the AI is unavailable, `runVerify` already shows "AI verdict temporarily unavailable" — good. Ensure `populateDetail` doesn't render the verdict block if `d.ai` is None (hide the "Get AI details" result area instead of showing dashes). Specifically in `runVerify`, if `d.maintained === null && d.reasoning === null`, show the unavailable message rather than dashes. The existing `.catch` handles network errors; add handling for a returned `d.error === "ai_unavailable"` to show a friendly "AI verdict unavailable right now" instead of dashes.

(c) Long-term correct fix (document in code comment / commit): the Supabase table needs an ALTER to add the missing columns. Since we can't run DDL here, the JSON-in-summary approach is the runtime fix; ALSO append the needed `ALTER TABLE` statements to `supabase_schema.sql` as a clearly-labeled migration block (new columns: maintained, maturity, community, docs, setup TEXT; reasoning TEXT; model TEXT) so the user can apply it in Supabase later. Keep `on_conflict="owner,name"` consistent.

## BUG 2 — Homepage cold-start "No cached repos in this category yet"
Confirmed: `routes/cron.py::POPULAR` uses free-text NL phrases ("termux", "ai agent", "automation", "web development", "fastapi", "react dashboard", "telegram bot", "rag", "next.js saas", "custom rom", "pdf tool", "cli tool") and calls `db.get_cached_search(q.lower())`. But the homepage loads `category=trending` / `termux` / `rom` etc. via `CATEGORY_QUERIES` keys, which are cached under key `"cat:" + category` (e.g. "cat:trending", "cat:termux"). The prewarm keys NEVER match the homepage category keys → prewarm does nothing useful for the category chips. So a cold visitor to `termux`/`ai-ml`/etc. sees the empty-state.

Fix: rewrite `routes/cron.py::POPULAR` to iterate over the SAME `CATEGORY_QUERIES` keys used by the homepage (import `CATEGORY_QUERIES` from `routes.search`, or define a list of those category keys here), and prewarm using the exact cache key the frontend requests. Each category should be prewarmed with its `CATEGORY_QUERIES[key]` query so the key `"cat:"+key` is populated. Keep the CRON_SECRET auth + error handling. Make sure prewarm uses `db.set_cached_search("cat:" + key, results)` exactly as the search route does. This ensures every category chip is populated on cold start.

Also confirm the GitHub Actions cron (`cron.yml`) hits `/api/prewarm` every 12 min — it does. Optionally also call `/api/search?category=<each>` is not needed; `/api/prewarm` is enough.

## BUG 3 — robots.txt blocks ALL crawling
`main.py::robots()` currently returns `"User-agent: *\nDisallow: /\n..."`. This disallows the entire site. Change `Disallow: /` to `Allow: /` (or `Disallow:` empty). Keep `Disallow: /api/` and the Sitemap line. Confirmed live regression.

## BUG 4 — Search flow timing / error handling (mostly OK, harden)
- Live test: `category=trending` returned HTTP 200 in ~3.3s. Acceptable. The search route already returns `{error:"rate_limit",...}` on 403 and `{error:"github_error",...}` on other errors; frontend `loadRepos` `.catch` clears rows and shows empty state. Good.
- Hardening: in `routes/search.py`, when `gh.search_repositories` raises a non-RuntimeError (e.g. network timeout / urllib.error.URLError), the bare `except RuntimeError` does NOT catch it → the exception propagates as a 500. Wrap the live search calls in the category branch AND keyword branch in a broader `except Exception` that returns the same rate_limit/github_error shape. (Currently `urllib.error.HTTPError` is a subclass of `RuntimeException`? No — HTTPError is not RuntimeError, so a 500/502 from GitHub currently 500s the endpoint.) Fix both branches to catch `Exception` and map to a friendly error JSON.
- GitHub API rate-limit: `gh.search_repositories` only raises `rate_limit_search` on HTTP 403, but GitHub returns 429 (Too Many Requests) for search rate limits too. In `lib/github.py`, also treat `e.code == 429` as rate_limit. And `get_repo_detail` doesn't handle rate limits at all (it just swallows exceptions returning partial data) — acceptable, but the search path must be graceful.

## BUG 5 — Mobile responsiveness
The frontend uses `max-width:680px` containers and is already viewport-meta tagged; mostly responsive. Quick wins: ensure the `.search-row` (input + smart-go button) stacks/wraps on narrow screens (<=420px) and the hero font scales down. Add a `@media (max-width:480px)` block if gaps exist (e.g. reduce `.hero h1` font-size, allow `.search-row` to be full-width). Keep changes minimal — only add what's needed so it looks good on 360–414px. The modal already has `@media (min-width:560px)`; verify the modal fits small screens (it does, overlay is relative). Don't over-engineer.

## BUG 6 — Homepage load time / cold start (Render free tier)
Live `category=trending` took 3.3s — that's warm. On a cold Render instance the first request after spin-down can take 30–50s and may time out the GitHub Actions prewarm curl. Mitigations to add (code + docs):
- In `routes/cron.py`, the `/api/prewarm` and `/api/keepalive` endpoints should respond FAST and do the heavy prewarming in the background (so the cron curl returns immediately and doesn't time out). Implement: when `/api/prewarm` is hit, return `{"prewarming": True}` immediately, then spawn a background thread (or `asyncio.create_task`) that iterates categories and fills the cache. Use a simple module-level threading.Thread with a daemon flag, guarded so two overlapping prewarms don't double-run (a `_prewarm_running` lock). This keeps the cron ping under a few seconds even on cold start.
- Keep the existing 12-min GitHub Action cron hitting `/health` (cheap, keeps alive) and `/api/prewarm` (now fast).
- No paid tier strictly required; the background-prewarm + keepalive cron is the free-tier solution. Note this in the final commit/notes.

## BUG 7 — AI verdict first-time latency (uncached)
First uncached verdict calls OpenRouter (timeout 40s) → if key missing, fails fast to Mistral (30s) → Gemini (30s) before returning ai_unavailable. The frontend already shows a loading skeleton during this. To reduce user wait when AI is configured but slow, the loading caption already cycles ("Checking README, commits & issues…"). Acceptable. Optionally: in `routes/verify.py`, on the cached path, return immediately; on fresh path, the frontend loading state covers it. No code change required beyond BUG 1(c) graceful-unavailable handling. If you find the provider chain wastes time, you may lower the OpenRouter/Mistral/Gemini timeouts to 25/20/20s — but only if it doesn't break working calls. Low priority; focus on BUG 1 and 2.

## BUG 8 — SEO / meta titles
- `main.py::repo_page()` already generates per-repo title/description/canonical/OG/schema.org into `templates/seo_repo.html`. This is server-rendered for `/repo/{owner}/{name}` and IS correct when the AI verdict populates (depends on BUG 1). Verify the template placeholders all get replaced (no leftover `__XXX__`). After BUG 1 fix, test `/repo/termux/termux-app` live returns proper `<title>`.
- `sitemap.xml` and `robots.txt` are live (sitemap confirmed working, robots.txt has the Disallow bug — BUG 3). Add the curated repo list is fine. Consider adding the popular category landing isn't needed (no category pages exist as URLs).
- Google Search Console submission is a manual step the user must do; document it in the final notes (provide the sitemap URL). We cannot submit programmatically.

## BUG 9 — Trust / polish: hero value prop & broken links
- Hero copy ("Find the repo that actually works. Ranked live from GitHub by stars. Tap any repo, then check it with AI.") is clear — ONE line value prop is present. Acceptable; leave as-is.
- Broken links: the `footer` and header nav "Saved" link currently point to `/` (no saved feature). The header nav `<span>Saved</span>` is non-functional (just a span, not a link) — fine, but ensure no `href="#"` dead links that look broken. The detail modal `dHomepage` uses `href="#"` as default then replaced — acceptable since it's replaced on populate. Verify there are no user-facing `reporadar-backend.onrender.com` branding strings (the API base is correct infra, not branding — leave it; it's not shown to users). The only "dev URL" concern: none are shown to end users. Confirm and report.
- `index.html.signal.bak` is a stale backup file — DELETE it from the repo (it's dead weight, shouldn't ship).

============================================================
DELIVERABLES FROM YOU (Opus)
============================================================
1. Fix files: `lib/supabase_client.py` (verdict read fallback + JSON-in-summary persistence + get_verified normalization), `routes/cron.py` (prewarm the real category keys + fast background prewarm), `routes/search.py` (broaden exception handling for rate_limit/429/network), `lib/github.py` (treat 429 as rate_limit), `main.py` (robots.txt Allow), `supabase_schema.sql` (append ALTER migration for missing AI columns), delete `static/index.html.signal.bak`, and `static/index.html` mobile media query if needed.
2. Run `python3 -m py_compile main.py routes/*.py lib/*.py` to ensure no syntax errors before finishing.
3. Report a concise summary of every change you made and why.
4. Do NOT commit or push. Hermes will review + commit + push + verify deploy.

Keep changes minimal and correct. Prefer editing existing functions over rewriting.
