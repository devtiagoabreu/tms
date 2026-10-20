// TMS Web client helpers

function qs(obj) {
  const params = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') params.set(k, v);
  });
  return params.toString();
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options || {});
  const text = await res.text();
  try { return { ok: res.ok, status: res.status, json: JSON.parse(text) }; }
  catch { return { ok: res.ok, status: res.status, json: null, text }; }
}

function fmtNumber(v, d=1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-';
  const n = Number(v);
  return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtInt(v) {
  if (v === null || v === undefined) return '-';
  return Number(v).toLocaleString();
}

function fmtDate(d) {
  if (!d) return '-';
  try { return new Date(d).toLocaleString(); } catch { return d; }
}

function tableRows(tbody, rows, mapFn) {
  tbody.innerHTML = '';
  if (!rows || rows.length === 0) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td colspan="100" class="muted">Sem dados</td>`;
    tbody.appendChild(tr);
    return;
  }
  rows.forEach(r => tbody.appendChild(mapFn(r)));
}

function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function setStatus(el, text, tone) {
  if (!el) return;
  el.innerHTML = `<span class="badge${tone ? ' badge-' + tone : ''}">${esc(text)}</span>`;
}

function initShell() {
  const root = document.documentElement;

  const toggle = document.getElementById('themeToggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('tms-theme', next); } catch (e) { /* ignore */ }
    });
  }

  const navToggle = document.getElementById('navToggle');
  const sidebar = document.getElementById('sidebar');
  if (navToggle && sidebar) {
    navToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initShell);
} else {
  initShell();
}

export { qs, fetchJSON, fmtNumber, fmtInt, fmtDate, tableRows, esc, setStatus };
