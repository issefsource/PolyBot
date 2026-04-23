let allResults = [];
let activeFilter = 'all';
let addedWallets = new Set();

function setFilter(cat, btn) {
  activeFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderResults();
}

function renderResults() {
  const container = document.getElementById('results');
  let data = allResults;
  if (activeFilter !== 'all') {
    data = data.filter(w => w.dominant_category === activeFilter);
  }
  if (!data.length) {
    container.innerHTML = '<div class="empty-state"><div>No wallets match this filter.</div></div>';
    return;
  }
  container.innerHTML = data.map((w, i) => {
    const rankClass = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
    const cardClass = i < 3 ? 'top' : i < 10 ? 'top2' : '';
    const scoreClass = w.insider_score >= 60 ? 'score-big' : w.insider_score >= 35 ? 'score-mid' : 'score-low';
    const isAdded = addedWallets.has(w.address);
    const nameHtml = w.username ? '<div class="wallet-name">' + w.username + '</div>' : '';
    const addr = w.address.slice(0, 6) + '...' + w.address.slice(-4);
    const signalTags = w.signals.map(s => '<span class="signal-tag">' + s + '</span>').join('');
    const signalLines = w.signals.join('<br>');
    const addedClass = isAdded ? 'added' : '';
    const addedLabel = isAdded ? '&#10003; ADDED' : '+ ADD';

    return [
      '<div class="wallet-card ' + cardClass + '" onclick="copyAddress(\'' + w.address + '\')">',
      '  <div class="rank ' + rankClass + '">' + (i + 1) + '</div>',
      '  <div class="wallet-info">',
      '    ' + nameHtml,
      '    <div class="wallet-addr">' + addr + '</div>',
      '    <div class="signals">' + signalTags + '</div>',
      '  </div>',
      '  <div class="score-cell">$' + w.avg_size.toLocaleString() + '</div>',
      '  <div class="score-cell">' + w.trade_count + '</div>',
      '  <div class="score-cell">' + w.early_score + '%</div>',
      '  <div><span class="cat-badge cat-' + w.dominant_category + '">' + w.dominant_category + '</span></div>',
      '  <div style="font-family:\'Space Mono\',monospace;font-size:10px;color:var(--muted)">' + signalLines + '</div>',
      '  <div style="display:flex;align-items:center;gap:10px">',
      '    <span class="score-cell ' + scoreClass + '">' + w.insider_score + '</span>',
      '    <button class="add-btn ' + addedClass + '" onclick="event.stopPropagation();addWallet(\'' + w.address + '\', this)">' + addedLabel + '</button>',
      '  </div>',
      '</div>'
    ].join('\n');
  }).join('\n');
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
            allResults.sort(function(a, b) { return b.insider_score - a.insider_score; });
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