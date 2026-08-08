/* RepoRadar frontend wiring — loads alongside your design HTML.
   Your index.html is untouched; this file connects search + verify to the API.
   Cards reuse your exact .card / .ring-wrap / .badge markup.
   NOTE: this script is injected at end of <body>, so the DOM is already ready. */

const fmtStars = n => n >= 1000 ? (n/1000).toFixed(1).replace(/\.0$/, '') + 'k' : '' + n;
const fmtDate = iso => {
  if (!iso) return 'unknown';
  const d = new Date(iso), days = (Date.now() - d) / 86400000;
  if (days < 1) return 'today';
  if (days < 30) return Math.floor(days) + ' days ago';
  if (days < 365) return Math.floor(days / 30) + ' months ago';
  return Math.floor(days / 365) + ' years ago';
};
const verdictClass = v => /working|✅/i.test(v) ? 'good' : /outdated|❌/i.test(v) ? 'bad' : 'warn';
const verdictLabel = v => /working|✅/i.test(v) ? 'Working' : /outdated|❌/i.test(v) ? 'Outdated' : 'Needs caution';
// ring offset: lower = more filled (your design: 8 full .. 63 empty)
const ringOffset = v => /good/i.test(v) ? 8 : /bad/i.test(v) ? 63 : 34;

function cardHTML(r, i, verdict) {
  const vc = verdict ? verdictClass(verdict) : 'warn';
  const off = verdict ? ringOffset(verdict) : 34;
  const label = verdict ? verdictLabel(verdict) : 'Click AI';
  const owner = r.owner, name = r.name;
  return `
  <div class="card" data-verdict="${vc}" id="card-${i}">
    <div class="ring-wrap">
      <svg><circle class="ring-track" cx="20" cy="20" r="16"></circle><circle class="ring-fill" cx="20" cy="20" r="16" style="--offset:${off}"></circle></svg>
      <div class="rank-txt">#${i + 1}</div>
    </div>
    <div class="repo-main">
      <div class="repo-top"><span class="repo-name"><span class="owner">${owner}/</span>${name}</span></div>
      <div class="repo-desc">${r.description || 'No description'}</div>
      <div class="stars"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14l-5-4.87 6.91-1.01z"/></svg>${fmtStars(r.stars)} · updated ${fmtDate(r.updated_at)}</div>
    </div>
    <button class="badge ${vc}" style="cursor:pointer;border:none;font:inherit;" onclick="verifyRepo('${owner}','${name}',${i})">
      <span class="pulse"></span>${label}
    </button>
  </div>`;
}

async function verifyRepo(owner, name, i) {
  const btn = document.querySelector(`#card-${i} .badge`);
  const orig = btn.innerHTML;
  btn.innerHTML = '<span class="pulse"></span>Checking…';
  try {
    const r = await fetch(`/api/verify?owner=${encodeURIComponent(owner)}&name=${encodeURIComponent(name)}`);
    const d = await r.json();
    if (d.verdict) {
      const vc = verdictClass(d.verdict);
      btn.className = `badge ${vc}`;
      btn.style.cursor = 'pointer'; btn.style.border = 'none'; btn.style.font = 'inherit';
      btn.innerHTML = `<span class="pulse"></span>${verdictLabel(d.verdict)}`;
    } else {
      btn.innerHTML = orig;
      alert('AI unavailable: ' + (d.message || d.error || 'try again'));
    }
  } catch (e) {
    btn.innerHTML = orig;
  }
}

let debounce;
async function doSearch(q) {
  if (!q.trim()) return;
  const loading = document.getElementById('rr-loading');
  const results = document.getElementById('rr-results');
  loading.style.display = 'block'; results.style.display = 'none';
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const d = await r.json();
    loading.style.display = 'none';
    if (d.error) { alert(d.message || d.error); return; }
    const list = d.results || [];
    document.getElementById('rr-count').textContent = list.length;
    if (list.length === 0) {
      document.getElementById('rr-list').innerHTML = '<div style="text-align:center;padding:40px;color:var(--ink-soft);font-size:14px;">No repos found for that term.<br>Try a simpler query (e.g. "poco custom rom").</div>';
    } else {
      document.getElementById('rr-list').innerHTML = list.map((x, i) => cardHTML(x, i)).join('');
    }
    results.style.display = 'block';
    document.querySelectorAll('#rr-list .card').forEach(c => c.classList.add('in-view'));
  } catch (e) {
    loading.style.display = 'none'; alert('Search failed');
  }
}

// --- init (DOM already ready because script is at end of <body>) ---
(function init() {
  // hide the static demo fallback so only live results show
  const fb = document.getElementById('staticFallback');
  if (fb) fb.style.display = 'none';

  const input = document.getElementById('searchInput');
  const wrap = document.createElement('div');
  wrap.innerHTML = `
    <div id="rr-loading" style="display:none;text-align:center;padding:40px;color:var(--ink-soft);font-family:'JetBrains Mono';font-size:13px;">⟳ Searching GitHub…</div>
    <div class="results-wrap" id="rr-results" style="display:none;">
      <div class="results-head"><h2><b id="rr-count">0</b> repos found</h2><span class="sort-tag">★ sorted by stars</span></div>
      <div id="rr-list"></div>
    </div>`;
  const footer = document.querySelector('footer');
  if (footer) footer.before(wrap);

  // hide the static demo results block (your design's default) once live results render
  const origWrap = document.querySelector('.results-wrap:not(#rr-results):not(#staticFallback)');
  if (origWrap) origWrap.style.display = 'none';

  if (input) {
    input.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => doSearch(input.value), 450);
    });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(input.value); });
  }
})();
