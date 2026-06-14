(function () {
  'use strict';

  const root = document.getElementById('gst-console');
  if (!root) return;

  const tryUrl = root.dataset.tryUrl || '';
  const profileComplete = root.dataset.profileComplete === 'true';
  const partnerReady = root.dataset.partnerReady === 'true';
  const quotaEl = document.getElementById('gst-quota-remaining');

  const RETURN_LABELS = { R1: 'GSTR-1', R3B: 'GSTR-3B', R9: 'GSTR-9' };
  const PREFERENCE_LABELS = {
    Q: 'Quarterly',
    M: 'Monthly',
  };
  const QUARTER_PERIODS = {
    Q1: 'Apr – Jun',
    Q2: 'Jul – Sep',
    Q3: 'Oct – Dec',
    Q4: 'Jan – Mar',
  };
  const QUARTER_ORDER = ['Q1', 'Q2', 'Q3', 'Q4'];
  const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const RETURN_TYPE_ALIASES = {
    GSTR1: 'GSTR-1',
    GSTR3B: 'GSTR-3B',
    GSTR9: 'GSTR-9',
    R1: 'GSTR-1',
    R3B: 'GSTR-3B',
    R9: 'GSTR-9',
  };

  const tabButtons = root.querySelectorAll('[data-tab]');
  const panels = root.querySelectorAll('[data-panel]');

  function getCsrfToken() {
    const input = root.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatLabel(key) {
    return key
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function statusBadgeClass(status) {
    const normalized = String(status || '').trim().toLowerCase();
    if (normalized === 'active') return 'is-active';
    if (normalized === 'cancelled' || normalized === 'canceled' || normalized === 'suspended') {
      return 'is-inactive';
    }
    return 'is-neutral';
  }

  function extractPartnerInnerData(body) {
    if (!body || body.error) return null;
    const outer = body.data;
    if (!outer || typeof outer !== 'object') return null;
    const inner = outer.data && typeof outer.data === 'object' ? outer.data : null;
    return inner && !Array.isArray(inner) ? inner : null;
  }

  function extractGstinRecord(body) {
    const record = extractPartnerInnerData(body);
    if (!record) return null;
    if (!record.gstin && !record.lgnm && !record.tradeNam) return null;
    return record;
  }

  function extractPreferenceItems(body) {
    const inner = extractPartnerInnerData(body);
    if (!inner || !Array.isArray(inner.response) || !inner.response.length) return null;
    return inner.response;
  }

  function extractReturnFilings(body) {
    const inner = extractPartnerInnerData(body);
    if (!inner || !Array.isArray(inner.EFiledlist)) return null;
    return inner.EFiledlist;
  }

  function normalizeReturnType(value) {
    const normalized = String(value || '').trim().toUpperCase();
    return RETURN_TYPE_ALIASES[normalized] || String(value || '').trim() || '—';
  }

  function formatReturnPeriod(retPrd) {
    const raw = String(retPrd || '').trim();
    if (!raw) return '—';
    if (raw.length >= 6) {
      const year = raw.slice(-4);
      const monthNum = parseInt(raw.slice(0, raw.length - 4), 10);
      if (monthNum >= 1 && monthNum <= 12) {
        return `${MONTH_NAMES[monthNum - 1]} ${year}`;
      }
    }
    return raw;
  }

  function parseFilingDate(value) {
    const parts = String(value || '').trim().split('-');
    if (parts.length !== 3) return 0;
    const day = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10);
    const year = parseInt(parts[2], 10);
    if (!day || !month || !year) return 0;
    return new Date(year, month - 1, day).getTime();
  }

  function filingStatusClass(status) {
    const normalized = String(status || '').trim().toLowerCase();
    if (normalized === 'filed') return 'is-filed';
    if (normalized === 'pending' || normalized === 'not filed') return 'is-pending';
    return 'is-neutral';
  }

  function sortReturnFilings(items) {
    return [...items].sort((left, right) => {
      const leftDate = parseFilingDate(left.dof);
      const rightDate = parseFilingDate(right.dof);
      if (leftDate !== rightDate) return rightDate - leftDate;
      const leftPeriod = String(left.ret_prd || '');
      const rightPeriod = String(right.ret_prd || '');
      return rightPeriod.localeCompare(leftPeriod);
    });
  }

  function preferenceLabel(code) {
    const normalized = String(code || '').trim().toUpperCase();
    return PREFERENCE_LABELS[normalized] || normalized || '—';
  }

  function preferencePillClass(code) {
    const normalized = String(code || '').trim().toUpperCase();
    if (normalized === 'Q') return 'is-quarterly';
    if (normalized === 'M') return 'is-monthly';
    return 'is-neutral';
  }

  function sortQuarters(items) {
    return [...items].sort((left, right) => {
      const leftIndex = QUARTER_ORDER.indexOf(String(left.quarter || '').toUpperCase());
      const rightIndex = QUARTER_ORDER.indexOf(String(right.quarter || '').toUpperCase());
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
    });
  }

  function renderFollowup(gstin, actions, fy) {
    if (!gstin || !actions.length) return '';
    const buttons = actions
      .map(([tabId, label]) => {
        const fyAttr = fy ? ` data-fy="${escapeHtml(fy)}"` : '';
        return `<button type="button" class="btn btn-ghost btn-sm" data-gst-followup="${escapeHtml(tabId)}" data-gstin="${escapeHtml(gstin)}"${fyAttr}>${escapeHtml(label)}</button>`;
      })
      .join('');
    return `<div class="gst-gstin-followup">
      <p class="gst-gstin-followup-label">Explore this GSTIN further</p>
      <div class="gst-gstin-followup-actions">${buttons}</div>
    </div>`;
  }

  function renderLookupHero({ title, subtitle, gstin, fy, badgesHtml }) {
    return `<article class="gst-gstin-hero">
      <div class="gst-gstin-hero-top">
        <div class="gst-gstin-hero-badges">${badgesHtml || ''}</div>
      </div>
      <h3 class="gst-gstin-hero-name">${escapeHtml(title)}</h3>
      ${subtitle ? `<p class="gst-gstin-hero-trade">${escapeHtml(subtitle)}</p>` : ''}
      <div class="gst-gstin-hero-meta">
        ${
          gstin
            ? `<p class="gst-gstin-hero-gstin"><span class="gst-gstin-hero-gstin-label">GSTIN</span><code>${escapeHtml(gstin)}</code></p>`
            : ''
        }
        ${
          fy
            ? `<p class="gst-gstin-hero-gstin"><span class="gst-gstin-hero-gstin-label">Financial year</span><code>${escapeHtml(fy)}</code></p>`
            : ''
        }
      </div>
    </article>`;
  }

  function formatAddress(addr) {
    if (!addr || typeof addr !== 'object') return '';
    const parts = [
      addr.bno,
      addr.bnm,
      addr.flno,
      addr.st,
      addr.loc,
      addr.locality,
      addr.landmark,
      addr.dst,
      addr.stcd,
      addr.pncd,
    ]
      .map((part) => String(part || '').trim())
      .filter(Boolean);
    return parts.join(', ');
  }

  function kvRow(label, value) {
    const text = String(value || '').trim();
    if (!text) return '';
    return `<div class="gst-gstin-kv">
      <span class="gst-gstin-kv-label">${escapeHtml(label)}</span>
      <span class="gst-gstin-kv-value">${escapeHtml(text)}</span>
    </div>`;
  }

  function renderGstinCard(title, rowsHtml, extraClass) {
    if (!rowsHtml) return '';
    return `<section class="gst-gstin-card${extraClass ? ` ${extraClass}` : ''}">
      <h4 class="gst-gstin-card-title">${escapeHtml(title)}</h4>
      <div class="gst-gstin-card-body">${rowsHtml}</div>
    </section>`;
  }

  function renderGstinDetails(body) {
    const record = extractGstinRecord(body);
    if (!record) return '';

    const gstin = record.gstin || body.gstin || '';
    const legalName = record.lgnm || '';
    const tradeName = record.tradeNam || '';
    const status = record.sts || '';
    const showTradeName = tradeName && tradeName !== legalName;
    const natureOfBusiness = Array.isArray(record.nba) ? record.nba.filter(Boolean).join(', ') : '';
    const principal = record.pradr && typeof record.pradr === 'object' ? record.pradr : null;
    const principalAddress = principal && principal.addr ? formatAddress(principal.addr) : '';
    const additionalAddresses = Array.isArray(record.adadr) ? record.adadr : [];

    const heroBadges = [];
    if (status) {
      heroBadges.push(
        `<span class="gst-gstin-pill gst-gstin-pill-status ${statusBadgeClass(status)}">${escapeHtml(status)}</span>`
      );
    }
    if (record.einvoiceStatus) {
      heroBadges.push(
        `<span class="gst-gstin-pill gst-gstin-pill-einvoice">E-invoice ${escapeHtml(record.einvoiceStatus)}</span>`
      );
    }
    if (record.dty) {
      heroBadges.push(`<span class="gst-gstin-pill gst-gstin-pill-type">${escapeHtml(record.dty)}</span>`);
    }

    const profileRows = [
      kvRow('Taxpayer type', record.dty),
      kvRow('Constitution', record.ctb),
      kvRow('Nature of business', natureOfBusiness),
      kvRow('Registered on', record.rgdt),
      kvRow('Cancelled on', record.cxdt),
      kvRow('Last updated', record.lstupdt),
    ].join('');

    const jurisdictionRows = [
      kvRow('State jurisdiction', record.stj),
      kvRow('State code', record.stjCd),
      kvRow('Centre jurisdiction', record.ctj),
      kvRow('Centre code', record.ctjCd),
    ].join('');

    let addressHtml = '';
    if (principalAddress || (principal && principal.ntr)) {
      const addressBlock = principalAddress
        ? `<p class="gst-gstin-address">${escapeHtml(principalAddress)}</p>`
        : '';
      const natureRow = principal && principal.ntr ? kvRow('Place nature', principal.ntr) : '';
      addressHtml = renderGstinCard('Principal place of business', `${addressBlock}${natureRow}`, 'gst-gstin-card--wide');
    }

    const additionalHtml = additionalAddresses
      .map((entry, index) => {
        if (!entry || typeof entry !== 'object') return '';
        const addrText = entry.addr ? formatAddress(entry.addr) : '';
        const rows = [
          addrText ? `<p class="gst-gstin-address">${escapeHtml(addrText)}</p>` : '',
          entry.ntr ? kvRow('Place nature', entry.ntr) : '',
        ].join('');
        return renderGstinCard(`Additional place ${index + 1}`, rows);
      })
      .join('');

    const gridCards = [
      renderGstinCard('Business profile', profileRows),
      renderGstinCard('Tax jurisdiction', jurisdictionRows),
      addressHtml,
      additionalHtml,
    ]
      .filter(Boolean)
      .join('');

    const followupHtml = renderFollowup(gstin, [
      ['gst-preference', 'Check filing preferences'],
      ['gst-return-status', 'Check return status'],
    ]);

    const heroHtml = renderLookupHero({
      title: legalName || tradeName || 'Taxpayer',
      subtitle: showTradeName ? `Trading as ${tradeName}` : '',
      gstin,
      fy: '',
      badgesHtml: heroBadges.join(''),
    });

    return `<div class="gst-gstin-view">
      ${heroHtml}
      <div class="gst-gstin-grid">${gridCards}</div>
      ${followupHtml}
    </div>`;
  }

  function renderPreferenceDetails(body) {
    const items = extractPreferenceItems(body);
    if (!items) return '';

    const gstin = body.gstin || '';
    const fy = body.fy || '';
    const quarters = sortQuarters(items);
    const uniquePreferences = [...new Set(quarters.map((item) => String(item.preference || '').trim().toUpperCase()).filter(Boolean))];
    const summaryBadge =
      uniquePreferences.length === 1
        ? `<span class="gst-gstin-pill gst-gstin-pill-pref ${preferencePillClass(uniquePreferences[0])}">${escapeHtml(preferenceLabel(uniquePreferences[0]))} filing</span>`
        : '';

    const quarterCards = quarters
      .map((item) => {
        const quarter = String(item.quarter || '').trim().toUpperCase();
        const preference = String(item.preference || '').trim().toUpperCase();
        const period = QUARTER_PERIODS[quarter] || '';
        return `<article class="gst-pref-quarter">
          <div class="gst-pref-quarter-head">
            <span class="gst-pref-quarter-name">${escapeHtml(quarter || '—')}</span>
            ${period ? `<span class="gst-pref-quarter-period">${escapeHtml(period)}</span>` : ''}
          </div>
          <span class="gst-gstin-pill gst-gstin-pill-pref ${preferencePillClass(preference)}">${escapeHtml(preferenceLabel(preference))}</span>
        </article>`;
      })
      .join('');

    const followupHtml = renderFollowup(gstin, [['gst-return-status', 'Check return status']], fy);
    const heroHtml = renderLookupHero({
      title: 'Filing preferences',
      subtitle: 'GSTR-1 and GSTR-3B return frequency by quarter',
      gstin,
      fy,
      badgesHtml: summaryBadge,
    });

    return `<div class="gst-gstin-view gst-pref-view">
      ${heroHtml}
      <section class="gst-pref-panel">
        <h4 class="gst-gstin-card-title">Quarterly schedule</h4>
        <div class="gst-pref-quarter-grid">${quarterCards}</div>
        <p class="gst-pref-note">Q = Quarterly returns · M = Monthly returns</p>
      </section>
      ${followupHtml}
    </div>`;
  }

  function renderReturnStatusDetails(body) {
    const filings = extractReturnFilings(body);
    if (!filings) return '';

    const gstin = body.gstin || '';
    const fy = body.fy || '';
    const filterType = String(body.type || '').trim().toUpperCase();
    const sortedFilings = sortReturnFilings(filings);
    const filedCount = sortedFilings.filter((item) => String(item.status || '').toLowerCase() === 'filed').length;
    const returnFilterLabel = filterType ? normalizeReturnType(filterType) : 'All returns';

    const heroBadges = [
      `<span class="gst-gstin-pill gst-gstin-pill-return">${escapeHtml(returnFilterLabel)}</span>`,
      `<span class="gst-gstin-pill gst-gstin-pill-count">${escapeHtml(String(sortedFilings.length))} record${sortedFilings.length === 1 ? '' : 's'}</span>`,
    ].join('');

    let listHtml = '';
    if (!sortedFilings.length) {
      listHtml = '<p class="gst-return-empty">No filed returns were found for this financial year.</p>';
    } else {
      listHtml = `<div class="gst-return-list">${sortedFilings
        .map((item) => {
          const period = formatReturnPeriod(item.ret_prd);
          const returnType = normalizeReturnType(item.rtntype);
          const status = String(item.status || '').trim() || '—';
          const filedOn = String(item.dof || '').trim() || '—';
          const mode = String(item.mof || '').trim() || '—';
          const arn = String(item.arn || '').trim() || '—';
          const valid = String(item.valid || '').trim().toUpperCase();
          const validLabel = valid === 'Y' ? 'Valid' : valid === 'N' ? 'Invalid' : '—';
          const validClass = valid === 'Y' ? 'is-valid' : valid === 'N' ? 'is-invalid' : 'is-neutral';

          return `<article class="gst-return-item">
            <div class="gst-return-item-head">
              <div class="gst-return-item-primary">
                <span class="gst-return-period">${escapeHtml(period)}</span>
                <span class="gst-return-type">${escapeHtml(returnType)}</span>
              </div>
              <span class="gst-gstin-pill gst-gstin-pill-status ${filingStatusClass(status)}">${escapeHtml(status)}</span>
            </div>
            <div class="gst-return-item-meta">
              ${kvRow('Filed on', filedOn)}
              ${kvRow('Mode', mode)}
              ${kvRow('ARN', arn)}
              <div class="gst-gstin-kv">
                <span class="gst-gstin-kv-label">Validity</span>
                <span class="gst-gstin-kv-value"><span class="gst-gstin-pill gst-gstin-pill-valid ${validClass}">${escapeHtml(validLabel)}</span></span>
              </div>
            </div>
          </article>`;
        })
        .join('')}</div>`;
    }

    const followupHtml = renderFollowup(
      gstin,
      [
        ['gst-gstin-search', 'View GSTIN details'],
        ['gst-preference', 'Check filing preferences'],
      ],
      fy
    );
    const heroHtml = renderLookupHero({
      title: 'Return filing status',
      subtitle:
        filedCount === sortedFilings.length
          ? `${filedCount} return${filedCount === 1 ? '' : 's'} filed in this period`
          : `${filedCount} of ${sortedFilings.length} returns filed`,
      gstin,
      fy,
      badgesHtml: heroBadges,
    });

    return `<div class="gst-gstin-view gst-return-view">
      ${heroHtml}
      <section class="gst-return-panel">
        <h4 class="gst-gstin-card-title">Filed returns</h4>
        ${listHtml}
      </section>
      ${followupHtml}
    </div>`;
  }

  function renderSummary(body, endpointId) {
    if (body.error) {
      return `<div class="gst-result-message is-error">${escapeHtml(body.error)}</div>`;
    }

    if (endpointId === 'gst-gstin-search') {
      const details = renderGstinDetails(body);
      if (details) return details;
    }

    if (endpointId === 'gst-preference') {
      const details = renderPreferenceDetails(body);
      if (details) return details;
    }

    if (endpointId === 'gst-return-status') {
      const details = renderReturnStatusDetails(body);
      if (details) return details;
    }

    const rows = [];
    if (body.gstin) rows.push(['GSTIN', body.gstin]);
    if (body.fy) rows.push(['Financial year', body.fy]);
    if (body.type) rows.push(['Return type', RETURN_LABELS[body.type] || body.type]);

    const data = body.data;
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      Object.entries(data).slice(0, 12).forEach(([key, value]) => {
        if (value === null || value === undefined || typeof value === 'object') return;
        rows.push([formatLabel(key), String(value)]);
      });
    }

    if (!rows.length) {
      return '<div class="gst-result-message is-success">Lookup completed.</div>';
    }

    return `<dl class="gst-result-list">${rows
      .map(
        ([label, value]) =>
          `<div class="gst-result-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`
      )
      .join('')}</dl>`;
  }

  function canSubmit() {
    if (!profileComplete) {
      return 'Complete your company profile before running lookups.';
    }
    if (!partnerReady) {
      return 'GST network is unavailable right now. Please try again later.';
    }
    return '';
  }

  function updateQuota(headerValue) {
    if (headerValue && quotaEl) {
      quotaEl.textContent = headerValue;
    }
  }

  function activateTab(tabId) {
    tabButtons.forEach((btn) => {
      const active = btn.dataset.tab === tabId;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach((panel) => {
      panel.classList.toggle('is-active', panel.dataset.panel === tabId);
    });
  }

  function prefillGstinOnTab(tabId, gstin, fy) {
    const panel = root.querySelector(`[data-panel="${tabId}"]`);
    if (!panel) return;
    const gstinInput = panel.querySelector('input[name="gstin"]');
    if (gstinInput) gstinInput.value = gstin;
    const fyInput = panel.querySelector('input[name="fy"]');
    if (fy && fyInput) fyInput.value = fy;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const focusTarget = gstinInput || panel.querySelector('input[name="fy"], select[name="type"], button[type="submit"]');
    if (focusTarget && typeof focusTarget.focus === 'function') {
      focusTarget.focus({ preventScroll: true });
    }
  }

  function handleFollowupClick(event) {
    const trigger = event.target.closest('[data-gst-followup]');
    if (!trigger || !root.contains(trigger)) return;
    const tabId = trigger.dataset.gstFollowup;
    const gstin = trigger.dataset.gstin;
    const fy = trigger.dataset.fy;
    if (!tabId || !gstin) return;
    activateTab(tabId);
    prefillGstinOnTab(tabId, gstin, fy);
  }

  root.addEventListener('click', handleFollowupClick);

  tabButtons.forEach((btn) => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });

  root.querySelectorAll('.gst-console-form').forEach((form) => {
    const panel = form.closest('[data-panel]');
    const statusEl = form.querySelector('.gst-console-status');
    const resultsWrap = panel.querySelector('.gst-console-results');
    const summaryEl = panel.querySelector('.gst-console-results-summary');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const endpointId = form.dataset.endpoint;
      const blocked = canSubmit();
      if (blocked) {
        statusEl.textContent = blocked;
        return;
      }
      if (!endpointId || !tryUrl) return;

      const body = new FormData();
      body.set('endpoint', endpointId);
      new FormData(form).forEach((value, key) => {
        const trimmed = String(value).trim();
        if (trimmed) body.set(key, trimmed);
      });

      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      statusEl.textContent = 'Looking up…';
      resultsWrap.hidden = false;
      summaryEl.innerHTML = '<div class="gst-result-message">Fetching details…</div>';

      try {
        const response = await fetch(tryUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            Accept: 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          body,
        });
        const payload = await response.json();
        summaryEl.innerHTML = renderSummary(payload, endpointId);
        statusEl.textContent = response.ok ? '' : 'Something went wrong';
        updateQuota(response.headers.get('X-GST-Quota-Remaining'));
      } catch (err) {
        summaryEl.innerHTML = '<div class="gst-result-message is-error">We could not reach the GST service. Please try again.</div>';
        statusEl.textContent = '';
      } finally {
        submitBtn.disabled = false;
      }
    });
  });
})();
