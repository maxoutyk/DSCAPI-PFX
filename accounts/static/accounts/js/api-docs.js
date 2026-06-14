(function () {
  'use strict';
  const Snippets = window.ApiDocsSnippets;
  const Highlighter = window.ApiDocsHighlight;
  const LangIcons = window.ApiDocsLangIcons || {};
  const root = document.querySelector('[data-api-docs-root]');
  if (!root || !Snippets || !Highlighter) return;
  const catalogScriptId = root.dataset.catalogId || 'api-docs-catalog';
  const catalogEl = document.getElementById(catalogScriptId);
  if (!catalogEl) return;
  const embed = root.dataset.embed === 'true';
  const tryUrl = root.dataset.tryUrl || '';
  const pageTitle = root.dataset.pageTitle || 'API Docs';
  const defaultItemId = root.dataset.defaultItem || '';
  const catalog = JSON.parse(catalogEl.textContent);
  const defaults = catalog.defaults || {};
  const items = [];
  catalog.services.forEach((service) => {
    service.items.forEach((item) => {
      items.push({ ...item, service_id: service.id, service_title: service.title });
    });
  });
  const MOBILE_MQ = window.matchMedia(embed ? '(max-width: 960px)' : '(max-width: 1200px)');
  const q = (selector) => root.querySelector(selector);
  const els = {
    nav: q('#api-docs-nav'),
    search: q('#api-docs-search'),
    main: q('#api-docs-main'),
    center: q('#api-docs-center'),
    langTabs: q('#api-docs-lang-tabs'),
    codeRequest: q('#api-docs-code-request'),
    codeResponse: q('#api-docs-code-response'),
    codeRequestTitle: q('#api-docs-code-request-title'),
    copyRequest: q('#api-docs-copy-request'),
    copyResponse: q('#api-docs-copy-response'),
    exportPostman: q('#api-docs-export-postman'),
    exportAllPostman: document.getElementById('api-docs-export-all-postman'),
    responseTabs: root.querySelectorAll('[data-response-tab]'),
    codePanel: q('#api-docs-code-panel'),
    menuBtn: q('#api-docs-menu-btn'),
    backdrop: q('#api-docs-backdrop'),
    sidebar: q('#api-docs-sidebar'),
  };
  const codeRequestEl = els.codeRequest.querySelector('code') || els.codeRequest;
  const codeResponseEl = els.codeResponse.querySelector('code') || els.codeResponse;
  let activeId = '';
  let activeLang = 'curl';
  let activeResponse = 'success';
  let rawRequestSnippet = '';
  let rawResponseSnippet = '';
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function methodClass(method) {
    return method === 'GET' ? 'api-docs-method--get' : 'api-docs-method--post';
  }
  function navOpenClass() {
    return embed ? 'api-docs-embed-nav-open' : 'api-docs-nav-open';
  }
  function closeNav() {
    document.body.classList.remove(navOpenClass());
    if (els.menuBtn) els.menuBtn.setAttribute('aria-expanded', 'false');
    if (els.backdrop) els.backdrop.hidden = true;
  }
  function openNav() {
    document.body.classList.add(navOpenClass());
    if (els.menuBtn) els.menuBtn.setAttribute('aria-expanded', 'true');
    if (els.backdrop) els.backdrop.hidden = false;
  }
  function toggleNav() {
    if (document.body.classList.contains(navOpenClass())) {
      closeNav();
    } else {
      openNav();
    }
  }
  function positionCodePanel() {
    const mount = root.querySelector('#api-docs-code-mount');
    const panel = els.codePanel;
    if (!panel) return;
    if (MOBILE_MQ.matches && mount) {
      mount.appendChild(panel);
      panel.classList.add('is-inline');
    } else if (els.center) {
      els.center.appendChild(panel);
      panel.classList.remove('is-inline');
    }
  }
  function defaultValueForParam(name) {
    if (defaults[name] !== undefined && defaults[name] !== '') {
      return defaults[name];
    }
    if (name === 'fy') return '2024-25';
    if (name === 'type') return 'R1';
    return '';
  }
  function renderTryPanel(item) {
    if (!tryUrl || item.kind !== 'endpoint') return '';
    const fields = (item.parameters || [])
      .map((param) => {
        const value = defaultValueForParam(param.name);
        const required = param.required ? 'required' : '';
        const label = param.required
          ? `${escapeHtml(param.name)} <span class="required">*</span>`
          : escapeHtml(param.name);
        return `
          <label class="api-docs-try-field">
            <span class="api-docs-try-label">${label}</span>
            <input type="text" name="${escapeHtml(param.name)}" value="${escapeHtml(value)}" ${required} autocomplete="off" spellcheck="false">
          </label>`;
      })
      .join('');
    return `
      <div class="api-docs-panel" data-main-panel="try">
        <form class="api-docs-try-form" id="api-docs-try-form">
          <p class="api-docs-try-lead">Run this request using your portal session. Calls count against your GST quota.</p>
          <div class="api-docs-try-fields">${fields || '<p class="api-docs-lead">No query parameters.</p>'}</div>
          <div class="api-docs-try-actions">
            <button type="submit" class="btn btn-sm" id="api-docs-try-submit">Send request</button>
            <span class="api-docs-try-status" id="api-docs-try-status" aria-live="polite"></span>
          </div>
        </form>
        <pre class="api-docs-code-pre api-docs-code-pre--try" id="api-docs-try-result"><code>Response will appear here.</code></pre>
      </div>`;
  }
  function bindTryForm(item) {
    const form = root.querySelector('#api-docs-try-form');
    const statusEl = root.querySelector('#api-docs-try-status');
    const resultPre = root.querySelector('#api-docs-try-result');
    if (!form || !tryUrl) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const params = new URLSearchParams({ endpoint: item.id });
      new FormData(form).forEach((value, key) => {
        const trimmed = String(value).trim();
        if (trimmed) params.set(key, trimmed);
      });
      if (statusEl) statusEl.textContent = 'Sending…';
      if (resultPre) resultPre.classList.remove('api-docs-code-pre--error', 'api-docs-code-pre--success');
      try {
        const response = await fetch(`${tryUrl}?${params.toString()}`, {
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
        });
        const body = await response.json();
        const formatted = JSON.stringify(body, null, 2);
        if (statusEl) statusEl.textContent = `HTTP ${response.status}`;
        if (resultPre) {
          const codeEl = resultPre.querySelector('code') || resultPre;
          codeEl.textContent = formatted;
          resultPre.classList.add(response.ok ? 'api-docs-code-pre--success' : 'api-docs-code-pre--error');
          setHighlightedCode(resultPre, codeEl, formatted, response.ok ? 'json' : 'json-error');
        }
      } catch (err) {
        if (statusEl) statusEl.textContent = 'Request failed';
        if (resultPre) {
          const codeEl = resultPre.querySelector('code') || resultPre;
          const message = JSON.stringify({ error: String(err) }, null, 2);
          codeEl.textContent = message;
          resultPre.classList.add('api-docs-code-pre--error');
          setHighlightedCode(resultPre, codeEl, message, 'json-error');
        }
      }
    });
  }
  function renderNav(filter) {
    const query = (filter || '').trim().toLowerCase();
    els.nav.innerHTML = '';
    catalog.services.forEach((service) => {
      const matched = service.items.filter((item) => {
        if (!query) return true;
        const hay = `${item.title} ${item.id} ${item.path || ''}`.toLowerCase();
        return hay.includes(query);
      });
      if (!matched.length) return;
      const group = document.createElement('div');
      group.className = 'api-docs-nav-group';
      group.innerHTML = `<div class="api-docs-nav-group-title">${escapeHtml(service.title)}</div>`;
      matched.forEach((item) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'api-docs-nav-item' + (item.id === activeId ? ' is-active' : '');
        const methodBadge =
          item.kind === 'endpoint' && item.method
            ? `<span class="api-docs-method api-docs-method--nav ${methodClass(item.method)}">${escapeHtml(item.method)}</span>`
            : '';
        btn.innerHTML = `<span class="api-docs-nav-item-inner">${methodBadge}<span class="api-docs-nav-item-text">${escapeHtml(item.title)}</span></span>`;
        btn.dataset.itemId = item.id;
        btn.addEventListener('click', () => {
          selectItem(item.id, true);
          if (MOBILE_MQ.matches) closeNav();
        });
        group.appendChild(btn);
      });
      els.nav.appendChild(group);
    });
  }
  function renderParameters(params) {
    if (!params || !params.length) {
      return '<p class="api-docs-lead">No parameters.</p>';
    }
    return params
      .map((param) => {
        const req = param.required
          ? '<span class="required">*</span>'
          : '<span class="optional">optional</span>';
        return `
          <div class="api-docs-param">
            <div class="api-docs-param-name">${escapeHtml(param.name)} ${req}</div>
            <div class="api-docs-param-meta">${escapeHtml(param.type)}</div>
            <div class="api-docs-param-desc">${escapeHtml(param.description)}</div>
          </div>`;
      })
      .join('');
  }
  function renderResponses(responses) {
    if (!responses || !responses.length) return '<p class="api-docs-lead">—</p>';
    return responses
      .map(
        (row) => `
        <div class="api-docs-response-row">
          <span class="api-docs-status">${escapeHtml(String(row.status))}</span>
          <span>${escapeHtml(row.description)}</span>
        </div>`
      )
      .join('');
  }
  function renderGuideSections(sections) {
    if (!sections) return '';
    return sections
      .map((section) => {
        let body = '';
        if (section.body) {
          body = `<p>${section.body.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')}</p>`;
        }
        if (section.bullets) {
          body += `<ul>${section.bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join('')}</ul>`;
        }
        if (section.code) {
          const lang = section.code_lang || 'curl';
          const highlighted = Highlighter.highlight(section.code, lang);
          body += `<pre class="api-docs-code-pre api-docs-guide-code api-docs-code-pre--lang-${lang}"><code>${highlighted}</code></pre>`;
        }
        return `<div class="api-docs-section"><h3>${escapeHtml(section.title)}</h3>${body}</div>`;
      })
      .join('');
  }

  function setCodePanelVisible(visible) {
    els.codePanel.classList.toggle('is-hidden', !visible);
    els.center.classList.toggle('api-docs-center--solo', !visible);
  }
  function renderMain(item) {
    const breadcrumb = embed
      ? ''
      : `<div class="api-docs-breadcrumb">API / ${escapeHtml(item.service_title)} / <strong>${escapeHtml(item.title)}</strong></div>`;
    const title = `<h1 class="api-docs-title">${escapeHtml(item.title)}</h1>`;
    const lead = `<p class="api-docs-lead">${escapeHtml(item.description || '')}</p>`;
    let endpoint = '';
    if (item.kind === 'endpoint' && item.method && item.path) {
      endpoint = `
        <div class="api-docs-endpoint">
          <span class="api-docs-method ${methodClass(item.method)}">${escapeHtml(item.method)}</span>
          <span class="api-docs-path">${escapeHtml(item.path)}</span>
        </div>`;
    }
    const codeMount = '<div class="api-docs-code-mount" id="api-docs-code-mount"></div>';
    if (item.kind === 'guide') {
      els.main.innerHTML = breadcrumb + title + lead + renderGuideSections(item.sections);
      setCodePanelVisible(false);
      return;
    }

    setCodePanelVisible(true);
    const tryTab = tryUrl
      ? '<button type="button" class="api-docs-tab" data-main-tab="try">Try it</button>'
      : '';
    const tabs = `
      <div class="api-docs-tabs" role="tablist">
        <button type="button" class="api-docs-tab is-active" data-main-tab="params">Request parameters</button>
        <button type="button" class="api-docs-tab" data-main-tab="responses">Responses</button>
        ${tryTab}
      </div>
      <div class="api-docs-panel is-active" data-main-panel="params">${renderParameters(item.parameters)}</div>
      <div class="api-docs-panel" data-main-panel="responses">${renderResponses(item.responses)}</div>
      ${renderTryPanel(item)}`;
    els.main.innerHTML = breadcrumb + title + lead + endpoint + codeMount + tabs;
    els.main.querySelectorAll('[data-main-tab]').forEach((tab) => {
      tab.addEventListener('click', () => {
        const name = tab.dataset.mainTab;
        els.main.querySelectorAll('[data-main-tab]').forEach((row) => row.classList.toggle('is-active', row.dataset.mainTab === name));
        els.main.querySelectorAll('[data-main-panel]').forEach((panel) => panel.classList.toggle('is-active', panel.dataset.mainPanel === name));
      });
    });
    bindTryForm(item);
    positionCodePanel();
  }
  function renderLangTabs() {
    els.langTabs.innerHTML = '';
    Snippets.LANGS.forEach((lang) => {
      const meta = LangIcons[lang.id] || { label: lang.label, svg: '' };
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'api-docs-lang-tab' + (lang.id === activeLang ? ' is-active' : '');
      btn.dataset.lang = lang.id;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', lang.id === activeLang ? 'true' : 'false');
      btn.setAttribute('aria-label', meta.label || lang.label);
      btn.title = meta.label || lang.label;
      btn.innerHTML = meta.svg || '';
      btn.addEventListener('click', () => {
        activeLang = lang.id;
        renderLangTabs();
        const item = items.find((row) => row.id === activeId);
        if (item) renderCode(item, activeResponse);
      });
      els.langTabs.appendChild(btn);
    });
  }
  function langCssClass(lang) {
    return `api-docs-code-pre--lang-${lang}`;
  }
  function setHighlightedCode(preEl, codeEl, raw, lang) {
    codeEl.innerHTML = Highlighter.highlight(raw, lang);
    preEl.classList.toggle('api-docs-code-pre--error', lang === 'json-error');
  }
  function renderCode(item, responseKind) {
    if (item.kind === 'guide') {
      setCodePanelVisible(false);
      return;
    }

    setCodePanelVisible(true);
    activeResponse = responseKind;
    const spec = Snippets.buildRequestSpec(item, catalog.base_url);
    rawRequestSnippet = Snippets.generateSnippet(activeLang, spec);
    els.codeRequestTitle.textContent = `Sample request · ${Snippets.LANGS.find((l) => l.id === activeLang)?.label || 'cURL'}`;
    els.codeRequest.className = `api-docs-code-pre api-docs-code-pre--request ${langCssClass(activeLang)}`;
    setHighlightedCode(els.codeRequest, codeRequestEl, rawRequestSnippet, activeLang);
    const success = item.response_success_json || '{}';
    const failure = item.response_error_json || '{\n  "error": "Request failed."\n}';
    rawResponseSnippet = responseKind === 'error' ? failure : success;
    els.codeResponse.className = `api-docs-code-pre api-docs-code-pre--response ${
      responseKind === 'error' ? 'api-docs-code-pre--error' : 'api-docs-code-pre--success'
    }`;
    setHighlightedCode(
      els.codeResponse,
      codeResponseEl,
      rawResponseSnippet,
      responseKind === 'error' ? 'json-error' : 'json'
    );
    const canExport = item.kind === 'endpoint';
    els.exportPostman.disabled = !canExport;
  }
  function selectItem(itemId, pushHash) {
    const item = items.find((row) => row.id === itemId) || items[0];
    if (!item) return;
    activeId = item.id;
    activeLang = 'curl';
    renderNav(els.search.value);
    renderLangTabs();
    renderMain(item);
    renderCode(item, 'success');
    if (pushHash) {
      history.replaceState(null, '', `#${item.id}`);
    }
    document.title = embed ? `${pageTitle} — ${item.title} — IG E-Sign` : `${item.title} — API Docs — IG E-Sign`;
  }
  function copyText(text, button) {
    navigator.clipboard.writeText(text).then(() => {
      const prev = button.textContent;
      button.textContent = 'Copied';
      setTimeout(() => {
        button.textContent = prev;
      }, 1200);
    });
  }
  els.search.addEventListener('input', () => renderNav(els.search.value));
  if (els.menuBtn) els.menuBtn.addEventListener('click', toggleNav);
  if (els.backdrop) els.backdrop.addEventListener('click', closeNav);
  els.copyRequest.addEventListener('click', () => copyText(rawRequestSnippet, els.copyRequest));
  els.copyResponse.addEventListener('click', () => copyText(rawResponseSnippet, els.copyResponse));
  els.responseTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const kind = tab.dataset.responseTab;
      els.responseTabs.forEach((row) => row.classList.toggle('is-active', row.dataset.responseTab === kind));
      const item = items.find((row) => row.id === activeId);
      if (item) renderCode(item, kind);
    });
  });
  els.exportPostman.addEventListener('click', () => {
    const item = items.find((row) => row.id === activeId);
    if (!item) return;
    const collection = Snippets.buildPostmanCollection(items, catalog, item);
    const slug = item.id.replace(/[^a-z0-9-]+/gi, '-');
    Snippets.downloadJson(`ig-esign-${slug}.postman_collection.json`, collection);
  });
  if (els.exportAllPostman) {
    els.exportAllPostman.addEventListener('click', () => {
      const collection = Snippets.buildPostmanCollection(items, catalog, null);
      Snippets.downloadJson('ig-esign-api.postman_collection.json', collection);
    });
  }
  MOBILE_MQ.addEventListener('change', () => {
    positionCodePanel();
    if (!MOBILE_MQ.matches) closeNav();
  });
  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeNav();
  });
  renderLangTabs();
  const hashId = (location.hash || '').replace(/^#/, '');
  if (hashId && items.some((row) => row.id === hashId)) {
    selectItem(hashId, false);
  } else if (defaultItemId && items.some((row) => row.id === defaultItemId)) {
    selectItem(defaultItemId, false);
  } else {
    selectItem(items[0] ? items[0].id : '', false);
  }
  window.addEventListener('hashchange', () => {
    const id = (location.hash || '').replace(/^#/, '');
    if (id && items.some((row) => row.id === id)) {
      selectItem(id, false);
    }
  });

})();

