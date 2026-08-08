/* RepoRadar frontend wiring — loads alongside your Bento design HTML.
   Your index.html is untouched (except an id on the input); this file
   connects search + verify to the API and renders the bento grid. */

const fmtStars = n => n >= 1000 ? (n/1000).toFixed(1).replace(/\.0$/, '') + 'k' : '' + n;
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

// star svg markup reused from your theme
const starSvg = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14l-5-4.87 6.91-1.01z"/></svg>';

function tileHTML(r, i, verdict) {
  const vc = verdict ? verdictClass(verdict) : 'warn';
  const label = verdict ? verdictLabel(verdict) : 'Click AI';
  const owner = r.owner, name = r.name;
  if (i === 0) {
    // featured full-width tile
    return `
  <div class="tile featured" style="animation-delay:.04s">
    <span class="tag-top"><span class="star-ico">★</span> top pick</span>
    <div class="name"><span class="owner">${owner}/</span>${name}</div>
    <div class="desc">${r.description || 'No description available.'}</div>
    <div class="foot">
      <span class="stars">${starSvg}<b class="num">${fmtStars(r.stars)}</b></span>
      <span class="updated">updated ${fmtDate(r.updated_at)}</span>
      <button class="badge ${vc}" style="cursor:pointer;border:none;font:inherit;" onclick="verifyRepo('${owner}','${name}',0)"><span class="sw"></span>${label}</button>
    </div>
  </div>`;
  }
  // small tile
  return `
  <div class="tile small" style="animation-delay:${(i*0.06).toFixed(2)}s">
    <div class="top-row">
      <div>
        <div class="name"><span class="owner">${owner}/</span>${name}</div>
      </div>
      <span class="rank">#${i+1}</span>
    </div>
    <div class="desc">${r.description || 'No description available.'}</div>
    <div class="foot">
      <span class="stars">${starSvg}<b class="num">${fmtStars(r.stars)}</b></span>
      <button class="badge ${vc}" style="cursor:pointer;border:none;font:inherit;" onclick="verifyRepo('${owner}','${name}',${i})"><span class="sw"></span>${label}</button>
    </div>
  </div>`;
}

async function verifyRepo(owner, name, i) {
  const btn = document.querySelector(`#rr-list .tile:nth-child(${i+1}) .badge`) || document.querySelectorAll('#rr-list .badge')[i];
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

// init (script is at end of <body>, DOM ready)
(function init() {
  const input = document.getElementById('searchInput');
  // build live results container that mirrors your .bento grid
  const wrap = document.createElement('div');
  wrap.innerHTML = `
    <div id="rr-loading" style="display:none;text-align:center;padding:40px;color:var(--ink-soft);font-family:'JetBrains Mono';font-size:13px;">⟳ Searching GitHub…</div>
    <div class="bento" id="rr-results" style="display:none;">
      <div id="rr-list" style="grid-column:1/-1;display:grid;grid-template-columns:repeat(2,1fr);gap:14px;"></div>
    </div>`;
  const bento = document.querySelector('.bento');
  if (bento && bento.parentNode) bento.parentNode.insertBefore(wrap, bento.nextSibling);

  if (input) {
    input.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => doSearch(input.value), 450);
    });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(input.value); });
  }
})();
