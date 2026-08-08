/* RepoRadar frontend wiring — Bento theme.
   Your index.html is untouched (except id on input + a search button).
   This file: manual search button, card-click detail panel, AI popup
   with reasoning, and preserves all your theme animations. */

const fmtStars = n => n >= 1000 ? (n/1000).toFixed(1).replace(/\.0$/, '') + 'k' : '' + n;
const fmtNum = n => n >= 1000 ? (n/1000).toFixed(1).replace(/\.0$/, '') + 'k' : '' + n;
const fmtDate = iso => {
  if (!iso) return 'unknown';
  const d = new Date(iso), days = (Date.now() - d) / 86400000;
  if (days < 1) return 'today';
  if (days < 30) return Math.floor(days) + ' days ago';
  if (days < 365) return Math.floor(days/30) + ' months ago';
  return Math.floor(days/365) + ' years ago';
};
const verdictClass = v => /working|✅/i.test(v) ? 'good' : /outdated|❌/i.test(v) ? 'bad' : 'warn';
const verdictLabel = v => /working|✅/i.test(v) ? 'Working' : /outdated|❌/i.test(v) ? 'Outdated' : 'Caution';
const whyPrefix = v => /working|✅/i.test(v) ? '✅ Why it works' : /outdated|❌/i.test(v) ? '❌ Why it\'s outdated' : '⚠️ Why caution';
const starSvg = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14l-5-4.87 6.91-1.01z"/></svg>';

// ---- tile markup (mirrors your theme classes so animations apply) ----
function tileHTML(r, i, verdict) {
  const vc = verdict ? verdictClass(verdict) : 'warn';
  const label = verdict ? verdictLabel(verdict) : 'Click AI';
  const owner = r.owner, name = r.name;
  if (i === 0) {
    return `
  <div class="tile featured" style="animation-delay:.04s" data-owner="${owner}" data-name="${name}" role="button">
    <span class="tag-top"><span class="star-ico">★</span> top pick</span>
    <div class="name"><span class="owner">${owner}/</span>${name}</div>
    <div class="desc">${r.description || 'No description available.'}</div>
    <div class="foot">
      <span class="stars">${starSvg}<b class="num">${fmtStars(r.stars)}</b></span>
      <span class="updated">updated ${fmtDate(r.updated_at)}</span>
      <button class="badge ${vc}" type="button" data-verify="${owner}|${name}|0" style="cursor:pointer;border:none;font:inherit;"><span class="sw"></span>${label}</button>
    </div>
  </div>`;
  }
  return `
  <div class="tile small" style="animation-delay:${(i*0.06).toFixed(2)}s" data-owner="${owner}" data-name="${name}" role="button">
    <div class="top-row">
      <div><div class="name"><span class="owner">${owner}/</span>${name}</div></div>
      <span class="rank">#${i+1}</span>
    </div>
    <div class="desc">${r.description || 'No description available.'}</div>
    <div class="foot">
      <span class="stars">${starSvg}<b class="num">${fmtStars(r.stars)}</b></span>
      <button class="badge ${vc}" type="button" data-verify="${owner}|${name}|${i}" style="cursor:pointer;border:none;font:inherit;"><span class="sw"></span>${label}</button>
    </div>
  </div>`;
}

// ---- AI verify -> popup with reasoning ----
async function verifyRepo(owner, name, i) {
  const btn = document.querySelectorAll('#rr-list .badge')[i];
  if (!btn) return;
  const orig = btn.innerHTML;
  btn.innerHTML = '<span class="sw"></span>Checking…';
  try {
    const r = await fetch(`/api/verify?owner=${encodeURIComponent(owner)}&name=${encodeURIComponent(name)}`);
    const d = await r.json();
    if (d.verdict) {
      const vc = verdictClass(d.verdict);
      btn.className = `badge ${vc}`;
      btn.style.cursor = 'pointer'; btn.style.border = 'none'; btn.style.font = 'inherit';
      btn.innerHTML = `<span class="sw"></span>${verdictLabel(d.verdict)}`;
      showAIPopup(owner, name, d);
    } else {
      btn.innerHTML = orig;
      alert('AI unavailable: ' + (d.message || d.error || 'try again'));
    }
  } catch (e) {
    btn.innerHTML = orig;
  }
}

function showAIPopup(owner, name, d) {
  const vc = verdictClass(d.verdict);
  const panel = document.getElementById('rr-overlay');
  panel.querySelector('#ov-title').innerHTML = `<span class="owner">${owner}/</span>${name}`;
  panel.querySelector('#ov-verdict').className = `badge ${vc}`;
  panel.querySelector('#ov-verdict').innerHTML = `<span class="sw"></span>${verdictLabel(d.verdict)}`;
  panel.querySelector('#ov-reason').innerHTML = `
    <div class="reason-row"><span class="rl">Maintained</span><span class="rv">${d.maintained || '—'}</span></div>
    <div class="reason-row"><span class="rl">Maturity</span><span class="rv">${d.maturity || '—'}</span></div>
    <div class="reason-row"><span class="rl">Setup</span><span class="rv">${d.setup || '—'}</span></div>
    ${d.reasoning ? `<div class="reason-why ${vc}">
      <span class="why-label">${whyPrefix(d.verdict)}</span>
      <p>${escapeHtml(d.reasoning)}</p>
    </div>` : ''}`;
  // ensure ONLY the AI popup is open (close detail if it was open)
  document.getElementById('rr-detail').classList.remove('open');
  openOverlay('rr-overlay');
}

// ---- card click -> full detail panel ----
async function openDetail(owner, name) {
  const panel = document.getElementById('rr-detail');
  panel.querySelector('#dt-title').innerHTML = `<span class="owner">${owner}/</span>${name}`;
  panel.querySelector('#dt-body').innerHTML = '<div style="padding:30px;text-align:center;color:var(--ink-soft);font-family:JetBrains Mono;font-size:13px;">⟳ Loading…</div>';
  openOverlay('rr-detail');
  try {
    const r = await fetch(`/api/repo/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`);
    const d = await r.json();
    const det = d.detail || {};
    panel.querySelector('#dt-body').innerHTML = `
      <div class="dt-stats">
        <div><b>${fmtNum(det.stars||0)}</b><span>stars</span></div>
        <div><b>${fmtNum(det.forks||0)}</b><span>forks</span></div>
        <div><b>${det.language||'—'}</b><span>lang</span></div>
        <div><b>${fmtDate(det.pushed_at)}</b><span>updated</span></div>
      </div>
      <p class="dt-desc">${det.description || 'No description.'}</p>
      ${det.readme ? `<div class="dt-readme">${escapeHtml(det.readme.slice(0,1400))}</div>` : ''}
      <div class="dt-actions">
        <button class="badge warn" type="button" data-verify="${owner}|${name}|0" style="cursor:pointer;border:none;font:inherit;"><span class="sw"></span>AI Check</button>
        <a class="dt-link" href="${det.html_url||'#'}" target="_blank" rel="noopener">Open on GitHub →</a>
      </div>`;
  } catch (e) {
    panel.querySelector('#dt-body').innerHTML = '<div style="padding:30px;color:var(--bad);">Failed to load details.</div>';
  }
}

function escapeHtml(s){ return (s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ---- search (manual button, NO auto-search) ----
async function doSearch(q) {
  if (!q.trim()) return;
  const loading = document.getElementById('rr-loading');
  const results = document.getElementById('rr-results');
  const demo = document.querySelector('.bento:not(#rr-results)');
  if (demo) demo.style.display = 'none';
  loading.style.display = 'block'; results.style.display = 'none';
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const d = await r.json();
    loading.style.display = 'none';
    if (d.error) { alert(d.message || d.error); return; }
    const list = d.results || [];
    if (list.length === 0) {
      document.getElementById('rr-list').innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--ink-soft);font-size:14px;">No repos found for that term.<br>Try a simpler query (e.g. "poco custom rom").</div>';
    } else {
      document.getElementById('rr-list').innerHTML = list.map((x, i) => tileHTML(x, i)).join('');
    }
    results.style.display = 'grid';
  } catch (e) {
    loading.style.display = 'none'; alert('Search failed');
  }
}

// ---- overlay open/close with body scroll-lock ----
function openOverlay(id){
  document.body.style.overflow = 'hidden';
  document.documentElement.style.overflow = 'hidden';
  document.getElementById(id).classList.add('open');
}
function closeOverlay(id){
  document.getElementById(id).classList.remove('open');
  // only unlock body if NO other overlay is still open
  const anyOpen = document.querySelector('.overlay.open');
  if (!anyOpen) {
    document.body.style.overflow = '';
    document.documentElement.style.overflow = '';
  }
}

// ---- init ----
(function init() {
  const input = document.getElementById('searchInput');
  const btn = document.getElementById('searchBtn');

  const wrap = document.createElement('div');
  wrap.innerHTML = `
    <div id="rr-loading" style="display:none;text-align:center;padding:40px;color:var(--ink-soft);font-family:'JetBrains Mono';font-size:13px;">⟳ Searching GitHub…</div>
    <div class="bento" id="rr-results" style="display:none;">
      <div id="rr-list" style="grid-column:1/-1;display:grid;grid-template-columns:1fr;gap:14px;"></div>
    </div>

    <div class="overlay" id="rr-detail">
      <div class="overlay-inner">
        <button class="overlay-close" data-close="rr-detail">×</button>
        <h2 id="dt-title" class="dt-title"></h2>
        <div id="dt-body"></div>
      </div>
    </div>

    <div class="overlay" id="rr-overlay">
      <div class="overlay-inner">
        <button class="overlay-close" data-close="rr-overlay">×</button>
        <h2 id="ov-title" class="dt-title"></h2>
        <div id="ov-verdict" class="badge" style="margin:10px 0;"></div>
        <div id="ov-reason" class="reason-box"></div>
      </div>
    </div>`;
  const bento = document.querySelector('.bento');
  if (bento && bento.parentNode) bento.parentNode.insertBefore(wrap, bento.nextSibling);

  // hide the static demo bento on load (no placeholder text)
  const demo = document.querySelector('.bento:not(#rr-results)');
  if (demo) {
    demo.style.display = 'none';
  }

  // ---- event delegation for tiles + AI badges + overlay close ----
  document.addEventListener('click', e => {
    const closeBtn = e.target.closest('[data-close]');
    if (closeBtn) { closeOverlay(closeBtn.getAttribute('data-close')); return; }
    const verifyBtn = e.target.closest('[data-verify]');
    if (verifyBtn) {
      // AI Check button lives INSIDE the open detail panel → allow it
      const insideOpen = verifyBtn.closest('.overlay.open');
      if (!insideOpen && document.querySelector('.overlay.open')) return; // block if from background while another open
      e.stopPropagation();
      const [o, n, i] = verifyBtn.getAttribute('data-verify').split('|');
      verifyRepo(o, n, parseInt(i, 10) || 0);
      return;
    }
    // clicking a background card while an overlay is open → ignore (1 overlay at a time)
    if (document.querySelector('.overlay.open')) return;
    const tile = e.target.closest('[data-owner]');
    if (tile) { openDetail(tile.getAttribute('data-owner'), tile.getAttribute('data-name')); }
  });

  const run = () => doSearch(input.value);
  if (btn) btn.addEventListener('click', run);
  if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
  // NO input/auto-search listener — manual only
})();
