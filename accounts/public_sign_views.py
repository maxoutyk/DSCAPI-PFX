"""Public free PDF visual signature — no login required."""

from __future__ import annotations

import base64
import binascii

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from signPdf.visual_stamp import VisualStampError, stamp_pdf_with_signatures
from signPdf.validation import PdfValidationError, validate_pdf_bytes

from .forms import PublicSignForm
from .ratelimit import RATE_LIMIT_MESSAGE, is_rate_limited, record_rate_limit_hit
from .services import get_public_sign_artifact, get_public_sign_artifact_metadata, store_public_sign_artifact


def _session_key(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or ''


@require_http_methods(['GET', 'POST'])
def public_sign_view(request):
    if not request.session.session_key:
        request.session.create()

    form = PublicSignForm()

    if request.method == 'POST':
        if is_rate_limited(request, 'public_sign'):
            messages.error(request, RATE_LIMIT_MESSAGE)
        else:
            form = PublicSignForm(request.POST, request.FILES)
            if form.is_valid():
                pdf_data = form.cleaned_data['pdf_file'].read()
                signature_png = form.cleaned_data['signature_png']
                try:
                    validate_pdf_bytes(pdf_data)
                    stamped = stamp_pdf_with_signatures(
                        pdf_data,
                        signature_png=signature_png,
                        placements=form.cleaned_data['placements'],
                        signature_width_ratio=form.cleaned_data['signature_width_ratio'],
                    )
                except (PdfValidationError, VisualStampError) as exc:
                    messages.error(request, str(exc))
                else:
                    record_rate_limit_hit(request, 'public_sign')
                    original_name = form.cleaned_data['pdf_file'].name
                    stem = original_name.rsplit('.', 1)[0] if '.' in original_name else original_name
                    signer_label = form.cleaned_data.get('signer_name', '').strip()
                    artifact = store_public_sign_artifact(
                        session_key=_session_key(request),
                        stamped_pdf_data=stamped,
                        filename=f'{stem}-signed.pdf',
                        signer_name=signer_label,
                    )
                    request.session['public_sign_artifact_id'] = str(artifact.id)
                    request.session.modified = True
                    return redirect('public_sign_done')

    return render(request, 'accounts/public_sign.html', {'form': form})


@require_http_methods(['POST'])
def public_sign_preview_view(request):
    if is_rate_limited(request, 'public_sign_preview'):
        return JsonResponse({'error': RATE_LIMIT_MESSAGE}, status=429)

    pdf_file = request.FILES.get('pdf_file')
    if not pdf_file:
        return JsonResponse({'error': 'PDF file is required.'}, status=400)
    if pdf_file.size > settings.PORTAL_SIGN_MAX_UPLOAD_BYTES:
        return JsonResponse({'error': 'PDF file is too large.'}, status=400)

    try:
        pdf_data = pdf_file.read()
        validate_pdf_bytes(pdf_data)
        import fitz

        doc = fitz.open(stream=pdf_data, filetype='pdf')
        page_count = doc.page_count
        first_page = doc[0]
        width = round(first_page.rect.width, 2)
        height = round(first_page.rect.height, 2)
        doc.close()
    except PdfValidationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception:
        return JsonResponse({'error': 'Could not read PDF.'}, status=400)

    record_rate_limit_hit(request, 'public_sign_preview')
    return JsonResponse({
        'page_count': page_count,
        'page_width': width,
        'page_height': height,
    })


def _get_public_sign_download(request, *, include_pdf: bool = True):
    artifact_id = request.session.get('public_sign_artifact_id')
    if not artifact_id:
        return None
    session_key = _session_key(request)
    if include_pdf:
        loaded = get_public_sign_artifact(session_key=session_key, artifact_id=artifact_id)
        if not loaded:
            request.session.pop('public_sign_artifact_id', None)
            request.session.modified = True
            return None
        pdf_data, metadata = loaded
        return {'data': pdf_data, **metadata}

    metadata = get_public_sign_artifact_metadata(session_key=session_key, artifact_id=artifact_id)
    if metadata is None:
        request.session.pop('public_sign_artifact_id', None)
        request.session.modified = True
        return None
    return metadata


@require_http_methods(['GET'])
def public_sign_done_view(request):
    payload = _get_public_sign_download(request, include_pdf=False)
    if not payload:
        messages.error(request, 'Download link expired. Please sign the document again.')
        return redirect('public_sign')
    display = dict(payload)
    response = render(request, 'accounts/public_sign_done.html', {'result': display})
    # Ensure session cookie is persisted after redirect from POST.
    request.session.modified = True
    return response


@require_http_methods(['GET'])
def public_sign_download_view(request):
    payload = _get_public_sign_download(request)
    if not payload:
        messages.error(request, 'Download link expired. Please sign the document again.')
        return redirect('public_sign')

    response = HttpResponse(payload['data'], content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{payload["filename"]}"'
    return response
