(function () {
  'use strict';

  var config = document.getElementById('google-ads-config');
  if (!config) return;

  var adsId = config.dataset.adsId || '';
  if (!adsId) return;

  window.dataLayer = window.dataLayer || [];
  function gtag() {
    window.dataLayer.push(arguments);
  }
  window.gtag = gtag;
  gtag('js', new Date());
  gtag('config', adsId);
})();
