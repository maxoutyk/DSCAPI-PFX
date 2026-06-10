(function () {
  'use strict';

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (!btn) return;

    var targetId = btn.getAttribute('data-copy');
    var el = document.getElementById(targetId);
    if (!el) return;

    var text = el.textContent || el.innerText;
    navigator.clipboard.writeText(text.trim()).then(function () {
      var original = btn.textContent;
      btn.textContent = 'Copied!';
      btn.setAttribute('aria-label', 'Copied to clipboard');
      setTimeout(function () {
        btn.textContent = original;
      }, 2000);
    });
  });
})();
