(function () {
  'use strict';

  var STORAGE_THEME = 'ig-esign-theme';
  var STORAGE_SIDEBAR = 'ig-esign-sidebar-collapsed';

  function initTheme() {
    var stored = localStorage.getItem(STORAGE_THEME);
    var prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
    var theme = stored || (prefersLight ? 'light' : 'dark');
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);
  }

  function updateThemeIcon(theme) {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    btn.innerHTML = theme === 'dark'
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || 'dark';
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem(STORAGE_THEME, next);
    updateThemeIcon(next);
  }

  function initSidebar() {
    var sidebar = document.getElementById('sidebar');
    var toggle = document.getElementById('sidebar-toggle');
    var mobileBtn = document.getElementById('mobile-menu-btn');
    if (!sidebar) return;

    if (localStorage.getItem(STORAGE_SIDEBAR) === 'true') {
      sidebar.classList.add('is-collapsed');
    }

    if (toggle) {
      toggle.addEventListener('click', function () {
        sidebar.classList.toggle('is-collapsed');
        localStorage.setItem(STORAGE_SIDEBAR, sidebar.classList.contains('is-collapsed'));
      });
    }

    if (mobileBtn) {
      mobileBtn.addEventListener('click', function () {
        sidebar.classList.toggle('is-mobile-open');
      });
    }
  }

  function initUserMenu() {
    var btn = document.getElementById('user-menu-btn');
    var dropdown = document.getElementById('user-dropdown');
    if (!btn || !dropdown) return;

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      dropdown.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', dropdown.classList.contains('is-open'));
    });

    document.addEventListener('click', function () {
      dropdown.classList.remove('is-open');
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  function initTabs() {
    document.querySelectorAll('[data-tabs]').forEach(function (root) {
      root.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var target = btn.getAttribute('data-tab');
          root.querySelectorAll('.tab-btn').forEach(function (b) {
            b.classList.toggle('is-active', b === btn);
            b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
          });
          root.querySelectorAll('.tab-panel').forEach(function (panel) {
            panel.classList.toggle('is-active', panel.id === target);
          });
        });
      });
    });
  }

  function initUploadZone() {
    document.querySelectorAll('.upload-zone').forEach(function (zone) {
      var input = zone.querySelector('input[type="file"]');
      var label = zone.querySelector('.upload-filename');
      if (!input) return;

      ['dragenter', 'dragover'].forEach(function (evt) {
        zone.addEventListener(evt, function (e) {
          e.preventDefault();
          zone.classList.add('is-dragover');
        });
      });

      ['dragleave', 'drop'].forEach(function (evt) {
        zone.addEventListener(evt, function () {
          zone.classList.remove('is-dragover');
        });
      });

      input.addEventListener('change', function () {
        if (label && input.files.length) {
          label.textContent = input.files[0].name;
        }
      });
    });
  }

  function initNavActive() {
    var path = window.location.pathname;
    var items = document.querySelectorAll('.nav-item');
    var best = null;
    var bestLen = 0;
    items.forEach(function (item) {
      var href = item.getAttribute('href');
      if (!href) return;
      if (path === href || (path.startsWith(href) && href.length > 1)) {
        if (href.length > bestLen) {
          best = item;
          bestLen = href.length;
        }
      }
    });
    if (best) best.classList.add('is-active');
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initSidebar();
    initUserMenu();
    initTabs();
    initUploadZone();
    initNavActive();

    var themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
  });
})();
