(function () {
  'use strict';

  var previewUrl = window.PORTAL_SIGN_PREVIEW_URL;
  var pdfInput = document.getElementById('id_pdf_file');
  var canvas = document.getElementById('pdf-preview-canvas');
  var wrap = document.getElementById('pdf-preview-wrap');
  var empty = document.getElementById('pdf-preview-empty');
  var meta = document.getElementById('pdf-preview-meta');
  var submitBtn = document.getElementById('sign-submit-btn');
  var styleInput = document.getElementById('id_signature_style');

  if (!pdfInput || !previewUrl) {
    return;
  }

  function currentPdfFile() {
    return pdfInput.files && pdfInput.files[0] ? pdfInput.files[0] : null;
  }

  function rerunPreview() {
    var file = currentPdfFile();
    if (!file) return;
    analyzePdf(file);
  }

  function getCsrfToken() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function setMeta(text, isError) {
    if (!meta) return;
    meta.textContent = text;
    meta.style.color = isError ? 'var(--error, #c0392b)' : 'var(--text-secondary)';
  }

  function renderPdfPreview(file) {
    if (!window.pdfjsLib || !canvas) {
      return;
    }
    window.pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    var reader = new FileReader();
    reader.onload = function (ev) {
      var typed = new Uint8Array(ev.target.result);
      window.pdfjsLib.getDocument({ data: typed }).promise.then(function (pdf) {
        return pdf.getPage(1);
      }).then(function (page) {
        var viewport = page.getViewport({ scale: 1.2 });
        var context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        return page.render({ canvasContext: context, viewport: viewport }).promise;
      }).then(function () {
        if (wrap) wrap.style.display = 'block';
        if (empty) empty.style.display = 'none';
      }).catch(function () {
        setMeta('Could not render PDF preview.', true);
      });
    };
    reader.readAsArrayBuffer(file);
  }

  function analyzePdf(file) {
    var formData = new FormData();
    formData.append('pdf_file', file);
    if (styleInput && styleInput.value) {
      formData.append('signature_style', styleInput.value);
    }

    fetch(previewUrl, {
      method: 'POST',
      body: formData,
      headers: { 'X-CSRFToken': getCsrfToken() },
      credentials: 'same-origin',
    })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (result) {
        if (!result.ok) {
          setMeta(result.data.error || 'Preview failed.', true);
          if (submitBtn) submitBtn.disabled = true;
          return;
        }
        var d = result.data;
        var status = d.ready
          ? d.signature_slots + ' signature slot(s) found for "' + d.anchor_text + '".'
          : 'No anchor text "' + d.anchor_text + '" found — signing will fail.';
        setMeta(
          d.page_count + ' page(s) · ' + status,
          !d.ready
        );
        if (submitBtn) submitBtn.disabled = !d.ready;
      })
      .catch(function () {
        setMeta('Preview request failed.', true);
      });
  }

  pdfInput.addEventListener('change', function () {
    var file = currentPdfFile();
    if (!file) {
      if (wrap) wrap.style.display = 'none';
      if (empty) empty.style.display = 'block';
      if (submitBtn) submitBtn.disabled = false;
      return;
    }
    renderPdfPreview(file);
    analyzePdf(file);
  });

  if (styleInput) {
    styleInput.addEventListener('change', rerunPreview);
  }
})();
