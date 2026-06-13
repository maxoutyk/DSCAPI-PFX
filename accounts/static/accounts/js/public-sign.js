(function () {
  'use strict';

  var previewUrl = window.PUBLIC_SIGN_PREVIEW_URL;
  var form = document.getElementById('public-sign-form');
  if (!form || !previewUrl) return;

  var pdfInput = document.getElementById('id_pdf_file');
  var signerInput = document.getElementById('id_signer_name');
  var signatureDataInput = document.getElementById('id_signature_data');
  var placementsJsonInput = document.getElementById('id_placements_json');
  var signatureImageInput = document.getElementById('id_signature_image');
  var submitBtn = document.getElementById('public-sign-submit');
  var textGroup = document.getElementById('text-signature-group');
  var imageGroup = document.getElementById('image-signature-group');
  var sigCanvas = document.getElementById('signature-preview-canvas');
  var pdfCanvas = document.getElementById('pdf-preview-canvas');
  var placementWrap = document.getElementById('pdf-placement-wrap');
  var placementOverlay = document.getElementById('placement-overlay');
  var placementSigImg = document.getElementById('placement-signature-preview');
  var placementList = document.getElementById('placement-list');
  var placementSizeControl = document.getElementById('placement-size-control');
  var signatureSizeRange = document.getElementById('signature-size-range');
  var signatureSizeLabel = document.getElementById('signature-size-label');
  var signatureWidthRatioInput = document.getElementById('id_signature_width_ratio');
  var previewMeta = document.getElementById('pdf-preview-meta');
  var pageNav = document.getElementById('page-nav');
  var pageLabel = document.getElementById('page-label');
  var pagePrev = document.getElementById('page-prev');
  var pageNext = document.getElementById('page-next');
  var modeInputs = form.querySelectorAll('input[name="signature_mode"]');
  var signGrid = document.getElementById('public-sign-grid');
  var signOptions = document.getElementById('public-sign-options');
  var previewCard = document.getElementById('public-sign-preview-card');

  var pdfDoc = null;
  var pageCount = 0;
  var currentPage = 1;
  var placements = {};
  var uploadedImageDataUrl = '';
  var renderRequestId = 0;
  var placementListBound = false;
  var signatureWidthRatio = 0.27;
  var signatureAspect = 3.0;
  var pageWidthPt = 595;
  var pageHeightPt = 842;
  var dragState = null;
  var signaturePreviewUrl = '';

  function showSignWorkspace() {
    if (signGrid) signGrid.classList.add('is-ready');
    if (signOptions) signOptions.hidden = false;
    if (previewCard) previewCard.hidden = false;
  }

  function hideSignWorkspace() {
    if (signGrid) signGrid.classList.remove('is-ready');
    if (signOptions) signOptions.hidden = true;
    if (previewCard) previewCard.hidden = true;
    if (placementWrap) placementWrap.hidden = true;
    if (placementOverlay) placementOverlay.hidden = true;
    if (placementSizeControl) placementSizeControl.hidden = true;
    signaturePreviewUrl = '';
    if (placementList) placementList.hidden = true;
    if (previewMeta) previewMeta.textContent = '';
    pageCount = 0;
    placements = {};
    pdfDoc = null;
    syncPlacementsInput();
    updateSubmitState();
  }

  function getCsrfToken() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function currentMode() {
    var checked = form.querySelector('input[name="signature_mode"]:checked');
    return checked ? checked.value : 'text';
  }

  function placementCount() {
    return Object.keys(placements).length;
  }

  function syncSignatureWidthRatio() {
    if (signatureWidthRatioInput) {
      signatureWidthRatioInput.value = String(signatureWidthRatio);
    }
    if (signatureSizeRange) {
      signatureSizeRange.value = String(Math.round(signatureWidthRatio * 100));
    }
    if (signatureSizeLabel) {
      signatureSizeLabel.textContent = Math.round(signatureWidthRatio * 100) + '% of page width';
    }
  }

  function placementBoxFractions() {
    var widthFrac = signatureWidthRatio;
    var heightFrac = (signatureWidthRatio * pageWidthPt / signatureAspect) / pageHeightPt;
    return { widthFrac: widthFrac, heightFrac: heightFrac };
  }

  function refreshSignaturePreview(callback) {
    buildSignatureData(function (dataUrl) {
      signaturePreviewUrl = dataUrl || '';
      if (placementSigImg) {
        placementSigImg.src = signaturePreviewUrl;
      }
      if (signaturePreviewUrl) {
        var probe = new Image();
        probe.onload = function () {
          if (probe.width && probe.height) {
            signatureAspect = probe.width / probe.height;
          }
          updatePlacementOverlay();
          if (callback) callback();
        };
        probe.onerror = function () {
          updatePlacementOverlay();
          if (callback) callback();
        };
        probe.src = signaturePreviewUrl;
      } else {
        signatureAspect = 3.0;
        updatePlacementOverlay();
        if (callback) callback();
      }
    });
  }

  function updatePlacementOverlay() {
    if (!placementOverlay) return;
    var placement = placements[currentPage];
    if (!placement) {
      placementOverlay.hidden = true;
      return;
    }

    var fractions = placementBoxFractions();
    placementOverlay.hidden = false;
    placementOverlay.style.left = (placement.x * 100) + '%';
    placementOverlay.style.top = (placement.y * 100) + '%';
    placementOverlay.style.width = (fractions.widthFrac * 100) + '%';
    placementOverlay.style.height = (fractions.heightFrac * 100) + '%';

    if (signaturePreviewUrl) {
      placementOverlay.classList.remove('is-empty');
      if (placementSigImg && placementSigImg.src !== signaturePreviewUrl) {
        placementSigImg.src = signaturePreviewUrl;
      }
    } else {
      placementOverlay.classList.add('is-empty');
      if (placementSigImg) placementSigImg.removeAttribute('src');
    }
  }

  function showPlacementControls() {
    if (placementSizeControl) placementSizeControl.hidden = false;
  }

  function syncPlacementsInput() {
    if (!placementsJsonInput) return;
    var list = Object.keys(placements)
      .map(function (page) { return parseInt(page, 10); })
      .sort(function (a, b) { return a - b; })
      .map(function (page) {
        return { page: page, x: placements[page].x, y: placements[page].y };
      });
    placementsJsonInput.value = JSON.stringify(list);
  }

  function updateModeUi() {
    var isText = currentMode() === 'text';
    if (textGroup) textGroup.hidden = !isText;
    if (imageGroup) imageGroup.hidden = isText;
    updateSubmitState();
  }

  function renderCursivePreview() {
    if (!sigCanvas) return;
    var ctx = sigCanvas.getContext('2d');
    var name = signerInput ? signerInput.value.trim() : '';
    ctx.clearRect(0, 0, sigCanvas.width, sigCanvas.height);
    if (!name) return;
    ctx.fillStyle = '#1a2744';
    ctx.font = '700 42px "Dancing Script", cursive';
    ctx.textBaseline = 'middle';
    ctx.fillText(name, 16, sigCanvas.height / 2);
  }

  function buildSignatureData(callback) {
    if (currentMode() === 'text') {
      renderCursivePreview();
      callback(sigCanvas ? sigCanvas.toDataURL('image/png') : '');
      return;
    }
    if (uploadedImageDataUrl) {
      callback(uploadedImageDataUrl);
      return;
    }
    if (signatureImageInput && signatureImageInput.files && signatureImageInput.files[0]) {
      var reader = new FileReader();
      reader.onload = function (ev) {
        callback(ev.target.result || '');
      };
      reader.readAsDataURL(signatureImageInput.files[0]);
      return;
    }
    callback('');
  }

  function updateSubmitState() {
    if (!submitBtn) return;
    var hasPdf = pdfInput && pdfInput.files && pdfInput.files.length > 0;
    var hasSignature = false;
    if (currentMode() === 'text') {
      hasSignature = !!(signerInput && signerInput.value.trim());
    } else {
      hasSignature = !!(
        (signatureImageInput && signatureImageInput.files && signatureImageInput.files.length) ||
        uploadedImageDataUrl
      );
    }
    submitBtn.disabled = !(hasPdf && hasSignature && placementCount() > 0 && pageCount > 0);
  }

  function bindPlacementListEvents() {
    if (!placementList || placementListBound) return;
    placementListBound = true;
    placementList.addEventListener('click', function (event) {
      var viewBtn = event.target.closest('[data-action="view-page"]');
      if (viewBtn) {
        event.preventDefault();
        event.stopPropagation();
        var page = parseInt(viewBtn.getAttribute('data-page'), 10);
        if (!isNaN(page)) {
          goToPage(page);
        }
        return;
      }
      var removeBtn = event.target.closest('[data-action="remove-page"]');
      if (removeBtn) {
        event.preventDefault();
        event.stopPropagation();
        var removePage = parseInt(removeBtn.getAttribute('data-page'), 10);
        if (!isNaN(removePage)) {
          delete placements[removePage];
          syncPlacementsInput();
          renderPlacementList();
          updatePlacementOverlay();
          updateSubmitState();
          if (previewMeta) {
            previewMeta.textContent = placementCount()
              ? placementCount() + ' page(s) selected. Click the preview to add or move signatures.'
              : pageCount + ' page(s). Click the preview to place your signature.';
          }
        }
      }
    });
  }

  function goToPage(pageNum) {
    if (!pdfDoc || pageNum < 1 || pageNum > pageCount) return;
    renderPdfPage(pageNum);
    if (previewCard && typeof previewCard.scrollIntoView === 'function') {
      previewCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function renderPlacementList() {
    if (!placementList) return;
    var pages = Object.keys(placements)
      .map(function (page) { return parseInt(page, 10); })
      .sort(function (a, b) { return a - b; });

    placementList.innerHTML = '';
    if (!pages.length) {
      placementList.hidden = true;
      return;
    }

    placementList.hidden = false;
    pages.forEach(function (page) {
      var item = document.createElement('li');
      if (page === currentPage) item.className = 'is-active';

      var label = document.createElement('span');
      label.textContent = 'Page ' + page;

      var actions = document.createElement('span');
      actions.style.display = 'inline-flex';
      actions.style.gap = '8px';

      var jumpBtn = document.createElement('button');
      jumpBtn.type = 'button';
      jumpBtn.className = 'btn btn-secondary btn-sm';
      jumpBtn.textContent = page === currentPage ? 'Viewing' : 'View';
      jumpBtn.setAttribute('data-action', 'view-page');
      jumpBtn.setAttribute('data-page', String(page));
      if (page === currentPage) {
        jumpBtn.disabled = true;
      }

      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'btn btn-ghost btn-sm';
      removeBtn.textContent = 'Remove';
      removeBtn.setAttribute('data-action', 'remove-page');
      removeBtn.setAttribute('data-page', String(page));

      actions.appendChild(jumpBtn);
      actions.appendChild(removeBtn);
      item.appendChild(label);
      item.appendChild(actions);
      placementList.appendChild(item);
    });
  }

  function setPlacementFromFraction(x, y) {
    x = Math.max(0, Math.min(1, x));
    y = Math.max(0, Math.min(1, y));
    placements[currentPage] = { x: x, y: y };
    syncPlacementsInput();
    showPlacementControls();
    refreshSignaturePreview();
    renderPlacementList();
    updateSubmitState();

    if (previewMeta) {
      previewMeta.textContent = placementCount()
        ? placementCount() + ' page(s) selected. Drag the box to move it, or use the size slider.'
        : pageCount + ' page(s). Click the preview to place your signature.';
    }
  }

  function setPlacement(clientX, clientY) {
    if (!placementWrap || !pdfCanvas) return;
    var rect = pdfCanvas.getBoundingClientRect();
    var x = (clientX - rect.left) / rect.width;
    var y = (clientY - rect.top) / rect.height;
    setPlacementFromFraction(x, y);
  }

  function startOverlayDrag(clientX, clientY) {
    if (!placements[currentPage]) return;
    dragState = {
      page: currentPage,
      moved: false,
      startX: clientX,
      startY: clientY,
    };
  }

  function moveOverlayDrag(clientX, clientY) {
    if (!dragState || !pdfCanvas || dragState.page !== currentPage) return;
    if (Math.abs(clientX - dragState.startX) > 3 || Math.abs(clientY - dragState.startY) > 3) {
      dragState.moved = true;
    }
    var rect = pdfCanvas.getBoundingClientRect();
    var x = (clientX - rect.left) / rect.width;
    var y = (clientY - rect.top) / rect.height;
    placements[currentPage] = {
      x: Math.max(0, Math.min(1, x)),
      y: Math.max(0, Math.min(1, y)),
    };
    syncPlacementsInput();
    updatePlacementOverlay();
  }

  function endOverlayDrag() {
    if (!dragState) return;
    if (dragState.moved) {
      renderPlacementList();
      updateSubmitState();
    }
    dragState = null;
  }

  function renderPdfPage(pageNum) {
    if (!pdfDoc || !pdfCanvas) return;
    currentPage = pageNum;
    var requestId = ++renderRequestId;

    pdfDoc.getPage(pageNum).then(function (page) {
      if (requestId !== renderRequestId) return null;
      var baseViewport = page.getViewport({ scale: 1 });
      pageWidthPt = baseViewport.width;
      pageHeightPt = baseViewport.height;
      var viewport = page.getViewport({ scale: 1.15 });
      var context = pdfCanvas.getContext('2d');
      pdfCanvas.height = viewport.height;
      pdfCanvas.width = viewport.width;
      return page.render({ canvasContext: context, viewport: viewport }).promise;
    }).then(function (rendered) {
      if (requestId !== renderRequestId || rendered === null) return;
      if (placementWrap) placementWrap.hidden = false;
      if (pageLabel) pageLabel.textContent = 'Page ' + pageNum + ' of ' + pageCount;
      if (pagePrev) pagePrev.disabled = pageNum <= 1;
      if (pageNext) pageNext.disabled = pageNum >= pageCount;
      updatePlacementOverlay();
      renderPlacementList();
    }).catch(function () {
      if (requestId !== renderRequestId) return;
      if (previewMeta) previewMeta.textContent = 'Could not render this page.';
    });
  }

  function analyzePdf(file) {
    var formData = new FormData();
    formData.append('pdf_file', file);
    fetch(previewUrl, {
      method: 'POST',
      body: formData,
      headers: { 'X-CSRFToken': getCsrfToken() },
      credentials: 'same-origin',
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          hideSignWorkspace();
          if (previewMeta) previewMeta.textContent = result.data.error || 'Could not read PDF.';
          pageCount = 0;
          updateSubmitState();
          return;
        }
        showSignWorkspace();
        showPlacementControls();
        syncSignatureWidthRatio();
        pageCount = result.data.page_count || 0;
        currentPage = 1;
        placements = {};
        syncPlacementsInput();
        if (pageNav) pageNav.hidden = pageCount <= 1;
        if (previewMeta) {
          previewMeta.textContent = pageCount + ' page(s). Click the preview to place signatures on each page.';
        }
        if (!window.pdfjsLib) return;
        window.pdfjsLib.GlobalWorkerOptions.workerSrc =
          'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        var reader = new FileReader();
        reader.onload = function (ev) {
          window.pdfjsLib.getDocument({ data: new Uint8Array(ev.target.result) }).promise
            .then(function (pdf) {
              pdfDoc = pdf;
              renderPdfPage(currentPage);
              updateSubmitState();
            })
            .catch(function () {
              if (previewMeta) previewMeta.textContent = 'Could not render PDF preview.';
            });
        };
        reader.readAsArrayBuffer(file);
      });
  }

  if (pdfInput) {
    pdfInput.addEventListener('change', function () {
      if (!pdfInput.files || !pdfInput.files[0]) {
        hideSignWorkspace();
        return;
      }
      if (previewMeta) previewMeta.textContent = 'Loading preview…';
      analyzePdf(pdfInput.files[0]);
    });
  }

  if (signerInput) {
    signerInput.addEventListener('input', function () {
      renderCursivePreview();
      refreshSignaturePreview();
      updateSubmitState();
    });
  }

  if (signatureImageInput) {
    signatureImageInput.addEventListener('change', function () {
      if (!signatureImageInput.files || !signatureImageInput.files[0]) return;
      var reader = new FileReader();
      reader.onload = function (ev) {
        uploadedImageDataUrl = ev.target.result || '';
        refreshSignaturePreview();
        updateSubmitState();
      };
      reader.readAsDataURL(signatureImageInput.files[0]);
    });
  }

  modeInputs.forEach(function (input) {
    input.addEventListener('change', function () {
      updateModeUi();
      refreshSignaturePreview();
    });
  });

  if (signatureSizeRange) {
    signatureSizeRange.addEventListener('input', function () {
      signatureWidthRatio = parseInt(signatureSizeRange.value, 10) / 100;
      syncSignatureWidthRatio();
      updatePlacementOverlay();
    });
  }

  if (placementWrap) {
    placementWrap.addEventListener('click', function (event) {
      if (event.target.closest('#placement-overlay')) return;
      setPlacement(event.clientX, event.clientY);
    });
  }

  if (placementOverlay) {
    placementOverlay.addEventListener('pointerdown', function (event) {
      if (!placements[currentPage]) return;
      event.preventDefault();
      event.stopPropagation();
      placementOverlay.setPointerCapture(event.pointerId);
      startOverlayDrag(event.clientX, event.clientY);
    });
    placementOverlay.addEventListener('pointermove', function (event) {
      if (!dragState) return;
      event.preventDefault();
      moveOverlayDrag(event.clientX, event.clientY);
    });
    placementOverlay.addEventListener('pointerup', function (event) {
      if (!dragState) return;
      event.preventDefault();
      if (placementOverlay.hasPointerCapture(event.pointerId)) {
        placementOverlay.releasePointerCapture(event.pointerId);
      }
      endOverlayDrag();
    });
    placementOverlay.addEventListener('pointercancel', function () {
      endOverlayDrag();
    });
  }

  if (pagePrev) {
    pagePrev.addEventListener('click', function () {
      if (currentPage > 1) {
        goToPage(currentPage - 1);
      }
    });
  }

  if (pageNext) {
    pageNext.addEventListener('click', function () {
      if (currentPage < pageCount) {
        goToPage(currentPage + 1);
      }
    });
  }

  bindPlacementListEvents();

  form.addEventListener('submit', function (event) {
    if (form.dataset.signatureReady === '1') {
      return;
    }
    event.preventDefault();
    if (!placementCount()) {
      alert('Click on at least one page in the preview to place your signature.');
      return;
    }
    buildSignatureData(function (dataUrl) {
      if (!dataUrl) {
        alert('Add your name or upload a signature image.');
        return;
      }
      if (signatureDataInput) signatureDataInput.value = dataUrl;
      syncPlacementsInput();
      form.dataset.signatureReady = '1';
      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.submit();
      }
    });
  });

  updateModeUi();
  renderCursivePreview();
  syncSignatureWidthRatio();
})();
