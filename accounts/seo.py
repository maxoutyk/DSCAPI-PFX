"""SEO helpers for IG E-Sign public marketing pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.conf import settings
from django.http import HttpRequest


@dataclass(frozen=True)
class PublicPageSEO:
    url_name: str
    changefreq: str
    priority: float


# Public marketing pages included in sitemap.xml (extend as new pages ship).
PUBLIC_SITEMAP_PAGES: tuple[PublicPageSEO, ...] = (
    PublicPageSEO('home', 'daily', 1.0),
    PublicPageSEO('marketing_pricing', 'weekly', 0.9),
    PublicPageSEO('marketing_features', 'weekly', 0.8),
    PublicPageSEO('blog_index', 'daily', 0.7),
    PublicPageSEO('public_api_docs', 'weekly', 0.8),
    PublicPageSEO('public_sign', 'weekly', 0.8),
    PublicPageSEO('register', 'weekly', 0.7),
    PublicPageSEO('login', 'monthly', 0.5),
    PublicPageSEO('marketing_privacy', 'monthly', 0.3),
    PublicPageSEO('marketing_terms', 'monthly', 0.3),
)

OG_IMAGE_PATH = '/static/accounts/img/og-default.png'
OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
OG_IMAGE_ALT = (
    'IG E-Sign by Incite Gravity — digital PDF signing, GST, E-way bill, and e-invoice for India'
)

# Per-route defaults for <title>, meta description, and Open Graph on public pages.
PUBLIC_PAGE_META: dict[str, dict[str, str]] = {
    'home': {
        'title': 'IG E-Sign — Digital PDF Signing Platform | Incite Gravity',
        'description': (
            'Sign PDFs with Class 3 DSC USB tokens, PFX API, or browser. GSTIN lookups, '
            'E-way bill and e-invoice PDF print, audit trails, and developer-first tools '
            'from Incite Gravity.'
        ),
    },
    'public_api_docs': {
        'title': 'API Documentation — IG E-Sign | Incite Gravity',
        'description': (
            'REST API reference for IG E-Sign: PFX PDF signing, USB DSC jobs, GSTIN lookups, '
            'E-way bill print, e-invoice (IRN) print, authentication, and integration examples.'
        ),
    },
    'public_sign': {
        'title': 'Free PDF Sign — IG E-Sign | Incite Gravity',
        'description': (
            'Sign a PDF online for free with IG E-Sign. No account required for trial signing '
            'with visible watermark — upgrade for production Class 3 DSC signatures.'
        ),
    },
    'register': {
        'title': 'Register — IG E-Sign | Incite Gravity',
        'description': (
            'Create your IG E-Sign account. 100 free signatures per month, API keys, '
            'USB DSC agent support, GSTIN lookups, and E-way bill / e-invoice print for '
            'Indian businesses.'
        ),
    },
    'login': {
        'title': 'Sign in — IG E-Sign | Incite Gravity',
        'description': (
            'Sign in to IG E-Sign to manage API keys, certificates, USB signing, GSTIN lookups, '
            'and E-way bill / e-invoice PDF downloads.'
        ),
    },
    'marketing_features': {
        'title': 'Features — IG E-Sign | Incite Gravity',
        'description': (
            'Class 3 USB DSC signing, PFX API, portal PDF signing, GSTIN lookups, E-way bill '
            'and e-invoice print, audit trails, and developer tools — explore IG E-Sign features.'
        ),
    },
    'marketing_pricing': {
        'title': 'Pricing — IG E-Sign | Incite Gravity',
        'description': (
            'IG E-Sign pricing: Free plan with 100 signatures/month. Pro and Enterprise plans '
            'for higher volume DSC, API, GSTIN, E-way bill, and e-invoice needs.'
        ),
    },
    'blog_index': {
        'title': 'Blog — IG E-Sign | Incite Gravity',
        'description': (
            'Guides on Class 3 DSC USB signing, PFX API integration, GSTIN verification, '
            'E-way bill and e-invoice print, and digital signature workflows for Indian businesses.'
        ),
    },
    'marketing_privacy': {
        'title': 'Privacy Policy — IG E-Sign | Incite Gravity',
        'description': 'How Incite Gravity collects, uses, and protects data when you use IG E-Sign.',
    },
    'marketing_terms': {
        'title': 'Terms of Service — IG E-Sign | Incite Gravity',
        'description': (
            'Terms of service for the IG E-Sign digital signature, GSTIN lookup, '
            'E-way bill, and e-invoice platform.'
        ),
    },
}

# Paths blocked in robots.txt (prefix match unless noted).
ROBOTS_DISALLOW_PREFIXES: tuple[str, ...] = (
    '/admin/',
    '/api/',
    '/dashboard/',
    '/sign/free/preview/',
    '/sign/free/done/',
    '/sign/free/download/',
    '/invite/',
    '/verify-email/',
    '/resend-verification/',
    '/reset-password/',
    '/password-reset/',
)

DEFAULT_META_DESCRIPTION = (
    'IG E-Sign by Incite Gravity — Class 3 DSC USB token signing, PFX API, '
    'GSTIN lookups, E-way bill and e-invoice PDF print, and browser-based PDF signatures '
    'for businesses and developers. IT Excellence Redefined.'
)

BRAND_NAME = 'Incite Gravity'
PRODUCT_NAME = 'IG E-Sign'
TAGLINE = 'IT Excellence Redefined'


def site_base_url() -> str:
    return getattr(settings, 'SITE_URL', 'http://127.0.0.1:8080').rstrip('/')


def normalize_path(path: str) -> str:
    if not path.startswith('/'):
        path = f'/{path}'
    if path != '/' and not path.endswith('/'):
        path = f'{path}/'
    return path


def build_canonical_url(request: HttpRequest, *, path: str | None = None) -> str:
    """Return an absolute canonical URL without query strings."""
    normalized = normalize_path(path or request.path)
    return f'{site_base_url()}{normalized}'


def should_noindex(request: HttpRequest) -> bool:
    if getattr(request, 'user', None) and request.user.is_authenticated:
        return True
    path = request.path or '/'
    private_prefixes = (
        '/dashboard/',
        '/admin/',
        '/invite/',
        '/verify-email/',
        '/resend-verification/',
        '/reset-password/',
        '/password-reset/',
        '/sign/free/preview/',
        '/sign/free/done/',
        '/sign/free/download/',
    )
    return any(path.startswith(prefix) for prefix in private_prefixes)


def page_meta_for_request(request: HttpRequest) -> dict[str, str]:
    view_name = ''
    kwargs: dict = {}
    if getattr(request, 'resolver_match', None) and request.resolver_match:
        view_name = request.resolver_match.url_name or ''
        kwargs = request.resolver_match.kwargs or {}

    if view_name == 'blog_post':
        from .blog import get_post

        post = get_post(kwargs.get('slug', ''))
        if post:
            return {'title': post.seo_title, 'description': post.description}

    meta = PUBLIC_PAGE_META.get(view_name, {})
    title = meta.get('title') or f'{PRODUCT_NAME} | {BRAND_NAME}'
    description = meta.get('description') or DEFAULT_META_DESCRIPTION
    return {'title': title, 'description': description}


def og_image_url() -> str:
    return f'{site_base_url()}{OG_IMAGE_PATH}'


def robots_txt_lines() -> Iterable[str]:
    lines = ['User-agent: *', 'Allow: /']
    for prefix in ROBOTS_DISALLOW_PREFIXES:
        lines.append(f'Disallow: {prefix}')
    lines.append('')
    lines.append(f'Sitemap: {site_base_url()}/sitemap.xml')
    return lines
