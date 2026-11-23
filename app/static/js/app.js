const GAME = window.GAME || {bonus_short: 'MB', bonus_name: 'Mega Ball'};
let currentTickets = [];
let pastDraws = [];
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

async function api(url, options) {
  const res = await fetch(url, options);
  let data = {};
  try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* ---------------- Upload data ---------------- */
let chosenFile = null;

function showDataStatus(s) {
  const box = $('dataStatus');
  $('builtinHint').textContent = `(config.ini: ${s.builtin_file})`;
  if (s.source === 'workbook') {
    const sheet = s.sheet ? ` from sheet "${s.sheet}"` : '';
    const skipped = s.skipped_rows ? ` · ${s.skipped_rows} row(s) skipped` : '';
    box.textContent = `Loaded "${s.file_name}" — ${s.draws_loaded} draw(s)${sheet}${skipped}.`;
    box.classList.remove('error');
  } else {
    box.textContent = `Could not use "${s.file_name}": ${s.reason}. Tickets will use built-in defaults until a valid file or sheet is chosen.`;
    box.classList.add('error');
  }
  const sel = $('sheetSelect');
  sel.innerHTML = '';
  (s.sheets || []).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    if (name === s.sheet) opt.selected = true;
    sel.appendChild(opt);
  });
  $('sheetBox').hidden = !(s.sheets && s.sheets.length);
}

function setUploadMode(on) {
  $('uploadRow').hidden = !on;
}

function pickFile(file) {
  chosenFile = file || null;
  $('fileName').textContent = file ? file.name : 'No file chosen — or drop a .xlsx / .csv here';
}

// Something changed the data: refresh the past-draws list and clear old scores.
function dataChanged(status) {
  showDataStatus(status);
  loadDraws();
  render(currentTickets);
  renderHot();
  $('message').textContent = '';
}

async function loadDataStatus() {
  try { showDataStatus(await api('/api/data')); } catch (e) { $('dataStatus').textContent = e.message; }
}

$('dataFile').addEventListener('change', e => pickFile(e.target.files[0]));

const dz = $('dropzone');
['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', e => { if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0]); });

$('uploadBtn').onclick = async () => {
  if (!chosenFile) { $('dataStatus').textContent = 'Choose a file first.'; $('dataStatus').classList.add('error'); return; }
  const form = new FormData();
  form.append('file', chosenFile);
  $('uploadBtn').disabled = true;
  $('dataStatus').classList.remove('error');
  $('dataStatus').textContent = `Uploading "${chosenFile.name}"…`;
  try {
    dataChanged(await api('/api/data/upload', {method: 'POST', body: form}));
  } catch (e) {
    $('dataStatus').textContent = e.message; $('dataStatus').classList.add('error');
  } finally {
    $('uploadBtn').disabled = false;
  }
};

async function resetData() {
  pickFile(null);
  $('dataFile').value = '';
  try { dataChanged(await api('/api/data/reset', {method: 'POST'})); }
  catch (e) { $('dataStatus').textContent = e.message; $('dataStatus').classList.add('error'); }
}

$('resetBtn').onclick = async () => {
  await resetData();
  document.querySelector('input[name="dataSource"][value="upload"]').checked = true;
  setUploadMode(true);
};

document.querySelectorAll('input[name="dataSource"]').forEach(r => r.addEventListener('change', async () => {
  if (r.value === 'builtin' && r.checked) { await resetData(); setUploadMode(false); }
  if (r.value === 'upload' && r.checked) setUploadMode(true);
}));

$('sheetSelect').addEventListener('change', async () => {
  try {
    dataChanged(await api('/api/data/sheet', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sheet: $('sheetSelect').value}),
    }));
  } catch (e) { $('dataStatus').textContent = e.message; $('dataStatus').classList.add('error'); }
});

/* ---------------- Past drawings ---------------- */
async function loadDraws() {
  const sel = $('pastDraw');
  sel.length = 1; // keep "— choose a date —"
  try {
    const data = await api('/api/draws');
    pastDraws = data.draws || [];
    pastDraws.forEach((d, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = `${d.date} — ${d.white_numbers.join(', ')} + ${GAME.bonus_short} ${d.mega_ball}`;
      sel.appendChild(opt);
    });
  } catch (e) { /* draw list is optional; comparison still works manually */ }
}

$('pastDraw')?.addEventListener('change', () => {
  const idx = $('pastDraw').value;
  if (idx === '') return;
  const d = pastDraws[Number(idx)];
  const inputs = [...document.querySelectorAll('#whiteInputs input')];
  d.white_numbers.forEach((n, i) => { if (inputs[i]) inputs[i].value = n; });
  $('winningMega').value = d.mega_ball;
});

/* ---------------- Tickets ---------------- */
function matchLabel(r) {
  return `${r.white_matches} white${r.mega_match ? ' + ' + GAME.bonus_short : ''}`;
}

function render(tickets, results = null, boxId = 'tickets', name = 'Ticket', empty = 'Generate tickets to begin.') {
  const box = $(boxId);
  if (!tickets.length) { box.innerHTML = `<p class="empty">${empty}</p>`; return; }
  box.innerHTML = tickets.map((t, i) => {
    const r = results?.[i];
    const src = r || (t.matched_draw ? t : null);
    const hit = new Set(src?.matched_white_numbers || []);
    let score = '<div class="score"></div>';
    if (r) {
      score = `<div class="score">${matchLabel(r)}</div>`;
    } else if (t.reason) {
      score = `<div class="score reason">${esc(t.reason)}</div>`;
    } else if (t.matched_draw) {
      const d = t.matched_draw;
      score = `<div class="score">${matchLabel(t)}<div class="match-draw">${d.date}: ${d.white_numbers.join(' ')} + ${d.mega_ball}</div></div>`;
    }
    const balls = t.white_numbers.map(n => `<span class="ball${hit.has(n) ? ' hit' : ''}">${n}</span>`).join('');
    const bonusHit = (r ? r.mega_match : t.matched_draw && t.mega_match) ? ' hit' : '';
    return `<div class="ticket"><div class="ticket-name">${name} ${i + 1}</div><div class="balls">${balls}<span class="ball mega${bonusHit}">${t.mega_ball}</span></div>${score}</div>`;
  }).join('');
}

/* ---------------- Hot-Number Games ---------------- */
let hotTickets = [];
const HOT_EMPTY = 'Generate games from the most-drawn numbers.';

function renderHot(results = null) {
  render(hotTickets, results, 'hotTickets', 'Game', HOT_EMPTY);
}

function renderHotNumbers(data) {
  const chip = (h, mega) => `<div class="hot-chip"><span class="ball small${mega ? ' mega' : ''}">${h.number}</span><span>${h.times_drawn}&times;</span><span class="uses">${h.games_using} game${h.games_using === 1 ? '' : 's'}</span></div>`;
  $('hotNumbers').innerHTML =
    `<div class="hot-row"><div class="hot-label">Top white balls <span>(avg ${data.avg_white} draws each)</span></div><div class="hot-chips">${data.hot_white.map(h => chip(h, false)).join('')}</div></div>` +
    `<div class="hot-row"><div class="hot-label">Top ${GAME.bonus_name}s <span>(avg ${data.avg_bonus})</span></div><div class="hot-chips">${data.hot_bonus.map(h => chip(h, true)).join('')}</div></div>`;
  $('hotNumbers').hidden = false;
}

$('hotGenerate').onclick = async () => {
  const btn = $('hotGenerate');
  const q = `games=${encodeURIComponent($('hotGames').value)}&white_pool=${encodeURIComponent($('hotWhitePool').value)}&bonus_pool=${encodeURIComponent($('hotBonusPool').value)}`;
  btn.disabled = true;
  $('hotMessage').textContent = '';
  try {
    const data = await api(`/api/hot-games?${q}`);
    hotTickets = data.tickets;
    renderHot();
    renderHotNumbers(data);
    const n = hotTickets.length;
    $('hotMessage').textContent =
      `${n} game${n === 1 ? '' : 's'} from ${data.draws} drawings (${data.from_date} to ${data.to_date}).` +
      (n > 1 ? ` Any two games share at most ${data.max_shared} white ball${data.max_shared === 1 ? '' : 's'}.` : '') +
      (data.tie_note ? ` Note: ${data.tie_note}.` : '') +
      ' Same odds as any other ticket.';
    btn.textContent = 'Regenerate';
  } catch (e) {
    $('hotMessage').textContent = e.message;
  } finally {
    btn.disabled = false;
  }
};

$('hotClear').onclick = () => {
  hotTickets = [];
  renderHot();
  $('hotNumbers').hidden = true;
  $('hotMessage').textContent = '';
  $('hotGenerate').textContent = 'Generate';
};

$('generate').onclick = async () => {
  const count = $('count').value, strategy = $('strategy').value, target = $('target').value;
  const btn = $('generate');
  $('message').textContent = '';
  btn.disabled = true;
  btn.textContent = target ? 'Searching…' : 'Generating…';
  try {
    if (!target) {
      const data = await api(`/api/tickets?count=${encodeURIComponent(count)}&strategy=${encodeURIComponent(strategy)}`);
      currentTickets = data.tickets;
    } else {
      const [minWhite, bonus] = target.split(':');
      const data = await api(`/api/search?count=${encodeURIComponent(count)}&strategy=${encodeURIComponent(strategy)}&min_white=${minWhite}&bonus=${bonus}`);
      currentTickets = data.tickets;
      const n = data.tickets.length;
      $('message').textContent = (data.complete
        ? `Found ${n} ticket${n === 1 ? '' : 's'}`
        : `Stopped after ${data.seconds} s - found ${n} of ${data.requested}`)
        + ` after checking ${data.attempts.toLocaleString()} generated tickets against ${data.draws_checked} past drawings in ${data.seconds} s.`;
    }
    render(currentTickets);
  } catch (e) { $('message').textContent = e.message; }
  finally { btn.disabled = false; btn.textContent = 'Generate tickets'; }
};

$('clear').onclick = () => { currentTickets = []; render([]); $('message').textContent = ''; };

/* ---------------- Suggestion from the draw history ---------------- */
let aiTickets = [];

async function loadAiStatus() {
  try {
    const st = await api('/api/ai-status');
    $('aiKeyHint').textContent = st.available ? `(${st.model})` : '(no API key set - using built-in analysis)';
    if (!st.available) $('aiUseClaude').checked = false;
  } catch (e) { /* optional */ }
}

$('aiSuggest').onclick = async () => {
  const btn = $('aiSuggest');
  const useClaude = $('aiUseClaude').checked;
  btn.disabled = true;
  btn.textContent = useClaude ? 'Asking Claude…' : 'Working…';
  $('aiNote').textContent = '';
  try {
    const data = await api(`/api/suggest?games=${encodeURIComponent($('aiGames').value)}&ai=${useClaude ? 1 : 0}`);
    aiTickets = data.tickets;
    render(aiTickets, null, 'aiTickets', 'Game');
    $('aiSummary').innerHTML = data.summary.map(x => `<li>${esc(x)}</li>`).join('');
    $('aiSummary').hidden = !data.summary.length;
    $('aiSource').textContent = data.source_label;
    $('aiSource').className = `badge ${data.source}`;
    $('aiSource').hidden = false;
    $('aiNote').textContent = data.note || '';
    btn.textContent = 'New suggestion';
  } catch (e) {
    $('aiNote').textContent = e.message;
    btn.textContent = 'Get suggestion';
  } finally {
    btn.disabled = false;
  }
};

$('compare').onclick = async () => {
  if (!currentTickets.length && !hotTickets.length && !aiTickets.length) { $('message').textContent = 'Generate tickets or hot-number games first.'; return; }
  const winning_white = [...document.querySelectorAll('#whiteInputs input')].map(x => Number(x.value));
  const winning_mega = Number($('winningMega').value);
  const compareSet = tickets => api('/api/compare', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tickets, winning_white, winning_mega}),
  });
  const summary = (label, results) => {
    const best = Math.max(...results.map(x => x.white_matches));
    const mb = results.filter(x => x.mega_match).length;
    return `${label}: best ${best} white-ball match${best === 1 ? '' : 'es'}${mb ? `, ${GAME.bonus_name} on ${mb}` : ''}`;
  };
  try {
    const parts = [];
    if (currentTickets.length) {
      const data = await compareSet(currentTickets);
      render(currentTickets, data.results);
      parts.push(summary('Tickets', data.results));
    }
    if (hotTickets.length) {
      const data = await compareSet(hotTickets);
      renderHot(data.results);
      parts.push(summary('Hot-number games', data.results));
    }
    if (aiTickets.length) {
      const data = await compareSet(aiTickets);
      render(aiTickets, data.results, 'aiTickets', 'Game');
      parts.push(summary('Suggestions', data.results));
    }
    $('message').textContent = parts.join(' · ') + '.';
  } catch (e) { $('message').textContent = e.message; }
};

loadDataStatus();
loadDraws();
loadAiStatus();
