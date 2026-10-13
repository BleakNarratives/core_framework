(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const root = document.documentElement;
  const ringKey = 'berdical-ring';
  const revealKey = 'berdical-reveal';
  const scrubKey = 'berdical-scrubbed-signals';
  const allowedRings = new Set(['glass', 'forge', 'air']);
  let snapshot = null;
  let signals = [];
  let refreshTimer;

  const readSet = (key) => {
    try {
      const value = JSON.parse(localStorage.getItem(key) || '[]');
      return new Set(Array.isArray(value) ? value.filter((entry) => typeof entry === 'string') : []);
    } catch (_) { return new Set(); }
  };
  const writeSet = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify([...value])); } catch (_) { /* The current view remains usable without persistence. */ }
  };
  let scrubbed = readSet(scrubKey);
  let ring = 'glass';
  let reveal = true;
  try {
    const savedRing = localStorage.getItem(ringKey);
    if (allowedRings.has(savedRing)) ring = savedRing;
    reveal = localStorage.getItem(revealKey) !== 'false';
  } catch (_) { /* Default to all local signals. */ }

  const applyFilters = () => {
    $$('.ring-option').forEach((button) => {
      const active = button.dataset.ring === ring;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    root.dataset.ring = ring;
    const revealButton = $('#reveal-toggle');
    if (revealButton) {
      revealButton.setAttribute('aria-pressed', String(reveal));
      revealButton.innerHTML = reveal ? 'REVEAL / <b>ON</b>' : 'REVEAL / <b>OFF</b>';
    }
    $$('.signal-card').forEach((card) => {
      const pressure = Number($('#tilt-pressure')?.value || 0);
      const levelThreshold = { info: 35, review: 70, action: 92 }[card.dataset.level] || 101;
      const tiltHidden = pressure >= levelThreshold;
      const hidden = (!reveal && card.dataset.level === 'info') || (ring === 'forge' && card.dataset.level === 'info') || (ring === 'air' && card.dataset.level !== 'action') || scrubbed.has(card.dataset.signalId) || tiltHidden;
      card.hidden = hidden;
    });
    $$('.wormhole-card').forEach((card) => {
      const connectedOnly = ring === 'forge';
      const ghost = (!reveal && card.dataset.available === 'no') || (connectedOnly && card.dataset.available !== 'yes');
      card.classList.toggle('is-ghosted', ghost);
      card.setAttribute('aria-hidden', String(ghost));
      card.tabIndex = ghost ? -1 : 0;
    });
    const visible = $$('.signal-card').filter((card) => !card.hidden).length;
    const empty = $('.empty-signal');
    if (empty) empty.hidden = visible !== 0;
    const restore = $('#restore-strip');
    if (restore) {
      restore.hidden = scrubbed.size === 0;
      $('#restore-count').textContent = scrubbed.size ? `${scrubbed.size} dismissed signal${scrubbed.size === 1 ? '' : 's'}` : '';
    }
  };

  const renderSignals = () => {
    if (!snapshot) return;
    signals = snapshot.signals || [];
    const host = $('#signal-list');
    if (!host) return;
    host.replaceChildren();
    if (!signals.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-signal';
      empty.textContent = 'No open local signal. Intake a lead or visit a wormhole to choose the next move.';
      host.append(empty);
      return;
    }
    signals.forEach((signal) => {
      const card = document.createElement('article');
      card.className = 'signal-card';
      card.dataset.signalId = signal.id;
      card.dataset.level = signal.level;
      const level = document.createElement('span');
      level.className = 'signal-level';
      level.textContent = signal.level;
      const content = document.createElement('div');
      const title = document.createElement('h3');
      title.textContent = signal.title;
      const detail = document.createElement('p');
      detail.textContent = signal.detail;
      content.append(title, detail);
      const next = document.createElement('a');
      next.className = 'next-move';
      next.href = signal.href;
      next.textContent = `${signal.next_move} ↗`;
      const scrub = document.createElement('button');
      scrub.className = 'scrub-button';
      scrub.type = 'button';
      scrub.dataset.scrub = signal.id;
      scrub.setAttribute('aria-label', `Dismiss ${signal.title}`);
      scrub.textContent = '×';
      card.append(level, content, next, scrub);
      host.append(card);
    });
    $('#snapshot-time').textContent = new Date(snapshot.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    applyFilters();
  };

  const loadSnapshot = async () => {
    const button = $('#refresh-signals');
    if (button) { button.disabled = true; button.classList.add('is-loading'); }
    try {
      const response = await fetch('/api/control-room', { headers: { Accept: 'application/json' }, cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) throw new Error(`Local signal endpoint returned ${response.status}`);
      snapshot = await response.json();
      renderSignals();
      if (button) button.title = `Refreshed ${new Date(snapshot.generated_at).toLocaleTimeString()}`;
    } catch (error) {
      const host = $('#signal-list');
      if (host) {
        const warning = document.createElement('div');
        warning.className = 'empty-signal is-error';
        warning.textContent = `Local signal refresh failed: ${error.message}. Use the wormholes below to inspect available sources.`;
        host.prepend(warning);
      }
    } finally {
      if (button) { button.disabled = false; button.classList.remove('is-loading'); }
    }
  };

  document.addEventListener('click', (event) => {
    const ringButton = event.target.closest('.ring-option');
    if (ringButton && allowedRings.has(ringButton.dataset.ring)) {
      ring = ringButton.dataset.ring;
      try { localStorage.setItem(ringKey, ring); } catch (_) { /* Current tab state still changes. */ }
      applyFilters();
      return;
    }
    if (event.target.closest('#reveal-toggle')) {
      reveal = !reveal;
      try { localStorage.setItem(revealKey, String(reveal)); } catch (_) { /* Current tab state still changes. */ }
      applyFilters();
      return;
    }
    const scrubButton = event.target.closest('[data-scrub]');
    if (scrubButton) {
      const id = scrubButton.dataset.scrub;
      if (scrubbed.has(id)) scrubbed.delete(id); else scrubbed.add(id);
      writeSet(scrubKey, scrubbed);
      applyFilters();
      renderTilt();
      return;
    }
    if (event.target.closest('#restore-signals')) {
      scrubbed.clear();
      writeSet(scrubKey, scrubbed);
      applyFilters();
      renderTilt();
    }
  });

  const tilt = $('#tilt-pressure');
  const tiltOutput = $('#tilt-output');
  const renderTilt = () => {
    if (!tilt || !tiltOutput) return;
    const pressure = Number(tilt.value);
    tiltOutput.textContent = `${pressure}% SCRUB`;
    $$('.signal-card').forEach((card) => {
      const shouldScrub = card.dataset.level === 'info' ? pressure >= 35 : card.dataset.level === 'review' ? pressure >= 70 : pressure >= 92;
      card.classList.toggle('tilt-candidate', pressure >= 35 && shouldScrub);
    });
    if (pressure >= 92) {
      $('#tilt-output').textContent = `${pressure}% · ACTION SIGNALS TOO`;
    }
    applyFilters();
  };
  tilt?.addEventListener('input', renderTilt);
  $('#restore-signals')?.addEventListener('click', () => {
    scrubbed.clear();
    writeSet(scrubKey, scrubbed);
    applyFilters();
    renderTilt();
  });

  $('#refresh-signals')?.addEventListener('click', loadSnapshot);
  if ($('#signal-list')) {
    loadSnapshot();
    refreshTimer = window.setInterval(loadSnapshot, 30000);
    window.addEventListener('beforeunload', () => window.clearInterval(refreshTimer), { once: true });
    if (tilt) renderTilt();
  }

  const pytchForms = $$('.pytch-stage-form');
  pytchForms.forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = $('button[type="submit"]', form);
    button.disabled = true;
    const token = $('input[name="_csrf_token"]', form)?.value || '';
    try {
      const response = await fetch(form.action, {
        method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'X-CSRF-Token': token },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Staging returned ${response.status}`);
      window.location.assign(data.redirect);
    } catch (error) {
      button.disabled = false;
      button.textContent = `Retry staging · ${error.message}`;
    }
  }));

  const scenarioForm = $('#scenario-form');
  const recovery = $('input[name="recovery_rate"]', scenarioForm || document);
  const recoveryOutput = $('#recovery-output');
  recovery?.addEventListener('input', () => { recoveryOutput.textContent = `${recovery.value}%`; });
  scenarioForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = $('#scenario-result');
    const button = $('button[type="submit"]', scenarioForm);
    button.disabled = true;
    result.classList.add('is-calculating');
    try {
      const payload = new URLSearchParams(new FormData(scenarioForm));
      payload.set('recovery_rate', String(Number(payload.get('recovery_rate')) / 100));
      const csrf = $('meta[name="csrf-token"]')?.content || '';
      const endpoint = scenarioForm.dataset.endpoint || '/tools/askhole/scenario';
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json', 'X-CSRF-Token': csrf }, body: payload,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.description || `Scenario returned ${response.status}`);
      $('strong', result).textContent = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(data.scenario_context_not_forecast);
      $('p', result).textContent = `${data.missed_calls} hypothetical calls × $${data.legacy_assumption_per_missed_call} imported estimate × ${(data.recovery_rate * 100).toFixed(0)}% assumed recovery. Source: ${data.source}. Unverified context, not a forecast.`;
      result.classList.add('has-result');
    } catch (error) {
      $('strong', result).textContent = 'Scenario unavailable';
      $('p', result).textContent = error.message;
    } finally {
      result.classList.remove('is-calculating');
      button.disabled = false;
    }
  });

  applyFilters();
})();
