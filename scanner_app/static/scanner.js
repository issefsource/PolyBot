let allResults = [];
let activeFilter = 'all';
let addedWallets = new Set();
// Single active sort: { key, dir }
let currentSort = { key: 'insider_score', dir: 'desc' };

function setSort(key, el) {
  if (currentSort.key === key) {
    currentSort.dir = currentSort.dir === 'desc' ? 'asc' : 'desc';
  } else {
    currentSort = { key, dir: 'desc' };
  }
  updateSortHeaders();
  renderResults();
}

function updateSortHeaders() {
  document.querySelectorAll('.grid-header div').forEach(div => {
    div.classList.remove('active-sort');
    const arrow = div.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = '';
  });
  const activeKey = currentSort.key;
  document.querySelectorAll('.grid-header div[data-sort]').forEach(div => {
    if (div.dataset.sort === activeKey) {
      div.classList.add('active-sort');
      const arrow = div.querySelector('.sort-arrow');
      if (arrow) arrow.textContent = currentSort.dir === 'desc' ? '▼' : '▲';
    }
  });
}

function setFilter(cat, btn) {
  activeFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderResults();
}

function renderResults() {
  const container = document.getElementById('results');
  let data = [...allResults];
  if (activeFilter !== 'all') {
    data = data.filter(w => w.dominant_category === activeFilter);
  }

  const { key, dir } = currentSort;
  data.sort((a, b) => {
    let valA = a[key];
    let valB = b[key];
    if (typeof valA === 'string') { valA = valA.toLowerCase(); valB = valB.toLowerCase(); }
    if (valA < valB) return dir === 'asc' ? -1 : 1;
    if (valA > valB) return dir === 'asc' ? 1 : -1;
    return 0;
  });

  if (!data.length) {
    container.innerHTML = '<div class="empty-state"><div>No wallets match this filter.</div></div>';
    return;
  }

  container.innerHTML = data.map((w, i) => {
    const rankClass = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
    const cardClass = i < 3 ? 'top' : i < 10 ? 'top2' : '';
    const scoreClass = w.insider_score >= 60 ? 'score-big' : w.insider_score >= 35 ? 'score-mid' : 'score-low';
    const isAdded = addedWallets.has(w.address);
    const nameHtml = w.username ? '<div class="wallet-name">' + escHtml(w.username) + '</div>' : '';
    const addr = w.address.slice(0, 6) + '...' + w.address.slice(-4);
    const signalTags = w.signals.map(s => '<span class="signal-tag">' + escHtml(s) + '</span>').join('');
    const addedClass = isAdded ? 'added' : '';
    const addedLabel = isAdded ? '&#10003; ADDED' : '+ ADD';

    // Win % cell: show value + open position badges
    const openBadges = [];
    if (w.open_winning > 0) openBadges.push('<span class="open-tag up">+' + w.open_winning + ' open ▲</span>');
    if (w.open_losing  > 0) openBadges.push('<span class="open-tag down">' + w.open_losing  + ' open ▼</span>');
    const winCellHtml = [
      '<div class="win-cell">',
      '  <span class="win-val score-cell">' + w.win_pct + '%</span>',
      openBadges.length ? '  <div class="open-badge">' + openBadges.join('') + '</div>' : '',
      '</div>'
    ].join('');

    return [
      '<div class="wallet-card col-grid ' + cardClass + '" onclick="copyAddress(\'' + w.address + '\')">',
      '  <div class="rank ' + rankClass + '">' + (i + 1) + '</div>',
      '  <div class="wallet-info">',
      '    ' + nameHtml,
      '    <div class="wallet-addr">' + addr + '</div>',
      '    <div class="signals">' + signalTags + '</div>',
      '  </div>',
      '  <div class="score-cell">$' + w.avg_size.toLocaleString() + '</div>',
      '  <div class="score-cell">' + w.trade_count + '</div>',
      '  ' + winCellHtml,
      '  <div class="score-cell">' + w.early_score + '%</div>',
      '  <div><span class="cat-badge cat-' + w.dominant_category + '">' + w.dominant_category + '</span></div>',
      '  <div class="score-action">',
      '    <span class="score-cell ' + scoreClass + '">' + w.insider_score + '</span>',
      '    <button class="add-btn ' + addedClass + '" onclick="event.stopPropagation();addWallet(\'' + w.address + '\', this)">' + addedLabel + '</button>',
      '    <a href="https://polymarket.com/profile/' + w.address + '" target="_blank" class="profile-btn" onclick="event.stopPropagation()">PROFILE</a>',
      '  </div>',
      '</div>'
    ].join('\n');
  }).join('\n');
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function copyAddress(addr) {
  navigator.clipboard.writeText(addr).then(() => {
    setStatus('Copied: ' + addr, false);
  });
}

function addWallet(addr, btn) {
  addedWallets.add(addr);
  btn.textContent = 'ADDED';
  btn.classList.add('added');
  navigator.clipboard.writeText(addr);
  setStatus('Address copied — paste it into viewer.py as a new whale', false);
}

function setStatus(msg, scanning) {
  document.getElementById('status-text').textContent = msg;
  const dot = document.getElementById('status-dot');
  dot.className = 'dot' + (scanning ? ' green' : '');
}

function setProgress(pct) {
  document.getElementById('progress').style.width = pct + '%';
}

async function startScan() {
  const btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = 'SCANNING...';
  setStatus('Fetching leaderboard...', true);
  setProgress(5);
  allResults = [];
  renderResults();

  try {
    const resp = await fetch('/api/scan');
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const result = await reader.read();
      if (result.done) break;
      buffer += decoder.decode(result.value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        try {
          const msg = JSON.parse(line);
          if (msg.type === 'progress') {
            setStatus(msg.text, true);
            setProgress(msg.pct);
          } else if (msg.type === 'result') {
            allResults.push(msg.data);
            renderResults();
          } else if (msg.type === 'done') {
            setStatus('Scan complete — ' + msg.count + ' wallets analyzed', false);
            setProgress(100);
            document.getElementById('last-scan').textContent = 'Last scan: ' + new Date().toLocaleTimeString();
          }
        } catch (e) {
          // skip malformed line
        }
      }
    }
  } catch (e) {
    setStatus('Scan failed: ' + e.message, false);
  }

  btn.disabled = false;
  btn.textContent = 'SCAN';
  setTimeout(function() { setProgress(0); }, 2000);
}

// Initialise sort header arrows on page load
document.addEventListener('DOMContentLoaded', updateSortHeaders);