"""Static blog content for IG E-Sign SEO content hub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BlogSection:
    heading: str
    paragraphs: tuple[str, ...]
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlogPost:
    slug: str
    title: str
    description: str
    published: date
    updated: date
    sections: tuple[BlogSection, ...]

    @property
    def seo_title(self) -> str:
        return f'{self.title} | IG E-Sign Blog'

    @property
    def url_path(self) -> str:
        return f'/blog/{self.slug}/'


BLOG_POSTS: tuple[BlogPost, ...] = (
    BlogPost(
        slug='class-3-dsc-usb-token-signing',
        title='How Class 3 DSC USB token signing works',
        description=(
            'Learn how Class 3 DSC USB tokens sign PDFs with PKCS#11, why the private key '
            'never leaves the token, and how IG E-Sign connects your API to a Windows agent.'
        ),
        published=date(2026, 6, 15),
        updated=date(2026, 7, 3),
        sections=(
            BlogSection(
                heading='Why Class 3 DSC still matters in India',
                paragraphs=(
                    'Indian businesses, CA firms, and ERP teams often need signatures backed by a '
                    'Class 3 Digital Signature Certificate on a USB token. The private key stays on '
                    'the hardware device, which is a common requirement for tax invoices, statutory '
                    'filings, and internal controls.',
                    'Cloud-only click-to-sign tools are useful for multi-party agreements, but they '
                    'do not replace token-based DSC workflows where the certificate must remain under '
                    'the signer’s physical control.',
                ),
            ),
            BlogSection(
                heading='The IG E-Sign USB signing flow',
                paragraphs=(
                    'IG E-Sign splits the work between your server and a Windows desktop agent on the '
                    'PC where the USB token is plugged in.',
                ),
                bullets=(
                    'Your server creates a signing job with the PDF and target device ID.',
                    'The Windows agent fetches the prepared job and prompts for the token PIN.',
                    'Signing happens locally via PKCS#11 — the private key never leaves the token.',
                    'Your server polls job status and downloads the signed PDF when complete.',
                ),
            ),
            BlogSection(
                heading='What you need to get started',
                paragraphs=(
                    'Pair the IG E-Sign Agent from your dashboard, keep it running in the system tray, '
                    'and call the USB signing API from your backend. Browser apps on ERP pages should '
                    'only talk to the local agent for the PIN step — never embed API keys in frontend code.',
                ),
            ),
        ),
    ),
    BlogPost(
        slug='pfx-api-pdf-signing',
        title='Sign PDFs with a PFX certificate over REST API',
        description=(
            'Use the IG E-Sign PFX API to sign PDFs server-side with an uploaded certificate or '
            'a saved portal alias, including placement styles and audit hashes.'
        ),
        published=date(2026, 6, 20),
        updated=date(2026, 7, 3),
        sections=(
            BlogSection(
                heading='When PFX API signing is the right fit',
                paragraphs=(
                    'PFX (PKCS#12) signing is ideal when your backend already holds a certificate '
                    'password and can call a REST API. It works well for automated invoice runs, '
                    'batch document processing, and integrations where a USB token is not required.',
                ),
            ),
            BlogSection(
                heading='Request shape',
                paragraphs=(
                    'Send a base64-encoded PDF, the PFX password, and either an inline PFX or a '
                    'certificate alias saved in the portal. Optional signature styles control visible '
                    'placement without hard-coding coordinates in every client.',
                ),
                bullets=(
                    'Authenticate with Authorization: Bearer dsc_live_…',
                    'Provide exactly one of pfx_base64 or cert_alias',
                    'Use signature_style to apply a named placement from the dashboard',
                    'Receive signed_pdf_base64 plus hash_before and hash_after prefixes',
                ),
            ),
            BlogSection(
                heading='Security notes',
                paragraphs=(
                    'Call the API only from trusted servers. Rotate keys if they leak, store PFX '
                    'passwords in a secrets manager, and rely on portal audit logs for compliance reviews.',
                ),
            ),
        ),
    ),
    BlogPost(
        slug='gstin-verification-for-signing-workflows',
        title='GSTIN verification for signing and onboarding workflows',
        description=(
            'How IG E-Sign GST lookups help verify taxpayer details before signing invoices, '
            'onboarding vendors, or automating compliance checks via API.'
        ),
        published=date(2026, 6, 28),
        updated=date(2026, 7, 3),
        sections=(
            BlogSection(
                heading='Why verify GSTIN before you sign',
                paragraphs=(
                    'Incorrect GSTINs create invoice mismatches, failed e-way bills, and reconciliation '
                    'noise. Pulling taxpayer details at onboarding or just before signing reduces '
                    'downstream corrections.',
                ),
            ),
            BlogSection(
                heading='What IG E-Sign exposes',
                paragraphs=(
                    'With a complete company profile, your account can look up GSTIN details, filing '
                    'preferences, and return status through the dashboard or REST API. GST usage is '
                    'metered separately from signing quotas.',
                ),
                bullets=(
                    'Get GSTIN details for any valid GSTIN within quota',
                    'Fetch preferences for a financial year',
                    'View return status filters such as R1, R3B, or R9',
                    'Print E-way bill and e-invoice (IRN) PDFs with NIC portal credentials',
                    'Use the same API key as signing services',
                ),
            ),
            BlogSection(
                heading='Pairing GST checks with PDF signing',
                paragraphs=(
                    'A common pattern is: verify the counterparty GSTIN, generate the invoice PDF, '
                    'sign with PFX or Class 3 USB DSC, then pull E-way bill or e-invoice PDFs when '
                    'you need the official printouts. One platform keeps audit trails for lookup, '
                    'print, and signature events.',
                ),
            ),
        ),
    ),
    BlogPost(
        slug='eway-bill-and-einvoice-pdf-print',
        title='Download E-way bill and e-invoice PDFs via API',
        description=(
            'How IG E-Sign prints E-way bill and e-invoice (IRN) PDFs from your dashboard or REST API '
            'using company profile NIC portal credentials.'
        ),
        published=date(2026, 7, 2),
        updated=date(2026, 7, 4),
        sections=(
            BlogSection(
                heading='Why print APIs matter for ERP teams',
                paragraphs=(
                    'After an invoice is signed and an IRN or E-way bill is generated on the GST network, '
                    'operations teams still need the official PDF printouts for transport, archives, and '
                    'customer portals. Pulling those PDFs through the same API key as signing keeps '
                    'integrations simple.',
                ),
            ),
            BlogSection(
                heading='E-way bill print',
                paragraphs=(
                    'IG E-Sign can download detailed, regular, or consolidate E-way bill PDFs using a '
                    '12-digit e-way bill number. Calls run through your tenant account with the GSTIN '
                    'and NIC portal credentials stored on your company profile.',
                ),
                bullets=(
                    'Detailed E-way bill print by e-way bill number',
                    'Regular and consolidate print variants for common logistics workflows',
                    'Binary PDF download or JSON with base64 for server-side ERP clients',
                ),
            ),
            BlogSection(
                heading='E-invoice print (IRN)',
                paragraphs=(
                    'For e-invoices, pass the 64-character Invoice Reference Number (IRN) to download '
                    'the official e-invoice PDF. The same company profile and API key used for GSTIN '
                    'lookups and signing apply — no separate product login for print.',
                ),
            ),
            BlogSection(
                heading='Setup checklist',
                paragraphs=(
                    'Complete your company profile, save encrypted NIC portal credentials, keep your '
                    'account Active, and call the print endpoints from a trusted backend. Never embed '
                    'API keys or NIC passwords in browser code.',
                ),
            ),
        ),
    ),
)

_POSTS_BY_SLUG = {post.slug: post for post in BLOG_POSTS}


def all_posts() -> tuple[BlogPost, ...]:
    return tuple(sorted(BLOG_POSTS, key=lambda post: post.published, reverse=True))


def get_post(slug: str) -> BlogPost | None:
    return _POSTS_BY_SLUG.get(slug)
