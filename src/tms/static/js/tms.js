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

async function initScreenDefaults() {
  const forms = Array.from(document.querySelectorAll('form')).filter((form) => {
    if (form.dataset.noAutoQuery !== undefined) return false;
    return Boolean(form.querySelector('[name="day_from"], [name="key"]'));
  });
  if (forms.length === 0) return;

  const result = await fetchJSON('/api/screens/latest-day');
  if (!result.ok || !result.json || !result.json.day) return;
  const day = result.json.day;

  forms.forEach((form) => {
    let touched = false;
    const from = form.querySelector('[name="day_from"]');
    const to = form.querySelector('[name="day_to"]');
    if (from && to && !from.value && !to.value) {
      from.value = day;
      to.value = day;
      touched = true;
    }
    const key = form.querySelector('[name="key"]');
    const period = form.querySelector('[name="period"]');
    if (key && !key.value && (!period || period.value === 'day')) {
      key.value = day;
      touched = true;
    }
    if (!touched) return;
    setTimeout(() => {
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      }
    }, 0);
  });
}

function initShell() {
  const root = document.documentElement;
  const isMobile = () => window.matchMedia('(max-width: 900px)').matches;

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
  const backdrop = document.getElementById('sidebarBackdrop');
  const groups = Array.from(document.querySelectorAll('.nav-group'));

  function readGroupState() {
    try {
      const value = JSON.parse(localStorage.getItem('tms-nav-groups') || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (e) {
      return {};
    }
  }

  const groupState = readGroupState();

  function persistGroupState() {
    try { localStorage.setItem('tms-nav-groups', JSON.stringify(groupState)); } catch (e) { /* ignore */ }
  }

  function isRail() {
    return !isMobile() && root.classList.contains('sidebar-collapsed');
  }

  function syncGroupAria() {
    const rail = isRail();
    groups.forEach((group) => {
      const btn = group.querySelector('.nav-group-toggle');
      if (!btn) return;
      const expanded = rail
        ? group.classList.contains('flyout-open')
        : !group.classList.contains('collapsed');
      btn.setAttribute('aria-expanded', String(expanded));
    });
  }

  function closeFlyouts(except) {
    groups.forEach((group) => {
      if (group !== except) group.classList.remove('flyout-open');
    });
    syncGroupAria();
  }

  function syncNavToggle() {
    if (!navToggle) return;
    if (isMobile()) {
      const open = Boolean(sidebar && sidebar.classList.contains('open'));
      navToggle.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
      navToggle.setAttribute('title', open ? 'Fechar menu' : 'Abrir menu');
      navToggle.setAttribute('aria-expanded', String(open));
      return;
    }
    const collapsed = root.classList.contains('sidebar-collapsed');
    navToggle.setAttribute('aria-label', collapsed ? 'Expandir menu' : 'Recolher menu');
    navToggle.setAttribute('title', collapsed ? 'Expandir menu' : 'Recolher menu');
    navToggle.setAttribute('aria-expanded', String(!collapsed));
  }

  function closeMobileNav() {
    if (sidebar) sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('visible');
    document.body.classList.remove('nav-open');
    syncNavToggle();
  }

  function setGroupExpanded(group, expanded, persist) {
    group.classList.toggle('collapsed', !expanded);
    if (persist) {
      groupState[group.dataset.navGroup] = expanded;
      persistGroupState();
    }
    syncGroupAria();
  }

  // Inicializa os grupos: o grupo da página atual começa aberto; os demais
  // seguem o estado salvo (ou ficam fechados para reduzir a altura do menu).
  groups.forEach((group) => {
    const key = group.dataset.navGroup;
    const hasActive = group.classList.contains('is-active');
    let expanded;
    if (hasActive) {
      expanded = true;
    } else if (Object.prototype.hasOwnProperty.call(groupState, key)) {
      expanded = Boolean(groupState[key]);
    } else {
      expanded = false;
    }
    setGroupExpanded(group, expanded, false);
  });

  groups.forEach((group) => {
    const btn = group.querySelector('.nav-group-toggle');
    if (!btn) return;
    btn.addEventListener('click', (event) => {
      event.stopPropagation();

      // No modo trilho (ícones), o clique abre o submenu em flyout.
      if (isRail()) {
        const open = !group.classList.contains('flyout-open');
        closeFlyouts(open ? group : null);
        group.classList.toggle('flyout-open', open);
        syncGroupAria();
        return;
      }

      setGroupExpanded(group, group.classList.contains('collapsed'), true);
    });
  });

  if (navToggle && sidebar) {
    navToggle.addEventListener('click', () => {
      if (isMobile()) {
        const open = sidebar.classList.toggle('open');
        if (backdrop) backdrop.classList.toggle('visible', open);
        document.body.classList.toggle('nav-open', open);
        if (!open) closeFlyouts(null);
        syncNavToggle();
        return;
      }
      root.classList.toggle('sidebar-collapsed');
      try {
        localStorage.setItem(
          'tms-sidebar-collapsed',
          root.classList.contains('sidebar-collapsed') ? '1' : '0',
        );
      } catch (e) { /* ignore */ }
      closeFlyouts(null);
      syncNavToggle();
    });
  }

  if (backdrop) backdrop.addEventListener('click', closeMobileNav);

  if (sidebar) {
    sidebar.querySelectorAll('.nav-item').forEach((link) => {
      link.addEventListener('click', () => {
        if (isMobile()) closeMobileNav();
        closeFlyouts(null);
      });
    });
  }

  document.addEventListener('click', (event) => {
    if (!isRail()) return;
    if (!event.target.closest('.nav-group')) closeFlyouts(null);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    closeFlyouts(null);
    if (isMobile()) closeMobileNav();
  });

  window.addEventListener('resize', () => {
    if (isMobile()) {
      closeFlyouts(null);
    } else {
      if (sidebar) sidebar.classList.remove('open');
      if (backdrop) backdrop.classList.remove('visible');
      document.body.classList.remove('nav-open');
      closeFlyouts(null);
    }
    syncNavToggle();
  });

  closeFlyouts(null);
  syncNavToggle();
  initScreenDefaults();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initShell);
} else {
  initShell();
}

export { qs, fetchJSON, fmtNumber, fmtInt, fmtDate, tableRows, esc, setStatus };
