import base64
import io
import json

import fitz
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from signPdf.visual_stamp import (
    SignaturePlacement,
    VisualStampError,
    stamp_pdf_with_signature,
    stamp_pdf_with_signatures,
    validate_signature_image,
)


def _minimal_pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), 'Sample document')
    data = doc.tobytes()
    doc.close()
    return data

def _signature_png(name: str = 'Alex Signer') -> bytes:
    image = Image.new('RGBA', (320, 96), (255, 255, 255, 0))
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image)
    draw.text((10, 28), name, fill=(20, 30, 60, 255))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


class VisualStampTests(TestCase):
    def test_validate_signature_image_rejects_empty(self):
        with self.assertRaises(VisualStampError):
            validate_signature_image(b'')

    def test_stamp_pdf_places_signature(self):
        pdf = _minimal_pdf()
        sig = _signature_png()
        stamped = stamp_pdf_with_signature(
            pdf,
            signature_png=sig,
            page_number=1,
            pos_x=0.7,
            pos_y=0.85,
        )
        self.assertTrue(stamped.startswith(b'%PDF'))
        self.assertGreater(len(stamped), len(pdf))

    def test_stamp_pdf_places_signatures_on_multiple_pages(self):
        pdf = _minimal_pdf(pages=3)
        sig = _signature_png()
        stamped = stamp_pdf_with_signatures(
            pdf,
            signature_png=sig,
            placements=[
                SignaturePlacement(page_number=1, pos_x=0.2, pos_y=0.8),
                SignaturePlacement(page_number=3, pos_x=0.7, pos_y=0.85),
            ],
        )
        self.assertTrue(stamped.startswith(b'%PDF'))
        self.assertGreater(len(stamped), len(pdf))

    def test_stamp_pdf_honors_signature_width_ratio(self):
        pdf = _minimal_pdf()
        sig = _signature_png()
        small = stamp_pdf_with_signatures(
            pdf,
            signature_png=sig,
            placements=[SignaturePlacement(page_number=1, pos_x=0.5, pos_y=0.5)],
            signature_width_ratio=0.12,
        )
        large = stamp_pdf_with_signatures(
            pdf,
            signature_png=sig,
            placements=[SignaturePlacement(page_number=1, pos_x=0.5, pos_y=0.5)],
            signature_width_ratio=0.35,
        )
        self.assertGreater(len(large), len(small))

class PublicSignViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('public_sign')

    def test_public_sign_page_is_public(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sign a PDF with your name')
        self.assertContains(response, 'visual signature only')

    def test_public_sign_accepts_name_signature(self):
        pdf = SimpleUploadedFile('doc.pdf', _minimal_pdf(), content_type='application/pdf')
        sig_b64 = base64.b64encode(_signature_png('Jane Doe')).decode('ascii')
        placements = json.dumps([{'page': 1, 'x': 0.7, 'y': 0.85}])
        response = self.client.post(
            self.url,
            {
                'pdf_file': pdf,
                'signature_mode': 'text',
                'signer_name': 'Jane Doe',
                'signature_data': 'data:image/png;base64,' + sig_b64,
                'placements_json': placements,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('public_sign_done'))

        done = self.client.get(reverse('public_sign_done'))
        self.assertEqual(done.status_code, 200)
        self.assertContains(done, 'Jane Doe')

        download = self.client.get(reverse('public_sign_download'))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Content-Type'], 'application/pdf')
        self.assertTrue(download.content.startswith(b'%PDF'))

    def test_public_sign_accepts_multiple_page_placements(self):
        pdf = SimpleUploadedFile('doc.pdf', _minimal_pdf(pages=3), content_type='application/pdf')
        sig_b64 = base64.b64encode(_signature_png('Jane Doe')).decode('ascii')
        placements = json.dumps([
            {'page': 1, 'x': 0.3, 'y': 0.8},
            {'page': 3, 'x': 0.6, 'y': 0.85},
        ])
        response = self.client.post(
            self.url,
            {
                'pdf_file': pdf,
                'signature_mode': 'text',
                'signer_name': 'Jane Doe',
                'signature_data': 'data:image/png;base64,' + sig_b64,
                'placements_json': placements,
            },
        )
        self.assertEqual(response.status_code, 302)
        download = self.client.get(reverse('public_sign_download'))
        self.assertEqual(download.status_code, 200)
        self.assertGreater(len(download.content), len(_minimal_pdf(pages=3)))

    def test_public_sign_accepts_signature_width_ratio(self):
        pdf = SimpleUploadedFile('doc.pdf', _minimal_pdf(), content_type='application/pdf')
        sig_b64 = base64.b64encode(_signature_png('Jane Doe')).decode('ascii')
        placements = json.dumps([{'page': 1, 'x': 0.7, 'y': 0.85}])
        response = self.client.post(
            self.url,
            {
                'pdf_file': pdf,
                'signature_mode': 'text',
                'signer_name': 'Jane Doe',
                'signature_data': 'data:image/png;base64,' + sig_b64,
                'placements_json': placements,
                'signature_width_ratio': '0.15',
            },
        )
        self.assertEqual(response.status_code, 302)