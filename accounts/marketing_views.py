"""Public marketing pages for IG E-Sign SEO."""

from __future__ import annotations

from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .blog import all_posts, get_post
from .seo import PUBLIC_PAGE_META, og_image_url, site_base_url
from .seo_schema import build_structured_data

PRICING_TIERS = (
    {
        'id': 'free',
        'name': 'Free',
        'price_label': '₹0',
        'period': 'per month',
        'description': 'For developers and teams evaluating IG E-Sign.',
        'signing_quota': '100 signatures / month',
        'gst_quota': '50 GST lookups / month',
        'highlights': (
            'PFX API & portal signing',
            'USB DSC agent (Windows)',
            'API keys & audit trail',
            'Company profile, GSTIN, E-way & e-invoice',
        ),
        'cta_label': 'Start for free',
        'cta_url_name': 'register',
        'featured': False,
    },
    {
        'id': 'pro',
        'name': 'Pro',
        'price_label': 'Contact us',
        'period': 'annual entitlement',
        'description': 'Higher quotas and production workloads for growing teams.',
        'signing_quota': 'Custom signing quota',
        'gst_quota': 'Custom GST quota',
        'highlights': (
            'Everything in Free',
            'Priority quota renewals',
            'Team members (when enabled)',
            'Dedicated onboarding support',
        ),
        'cta_label': 'Contact sales',
        'cta_url_name': 'marketing_contact',
        'featured': True,
    },
    {
        'id': 'enterprise',
        'name': 'Enterprise',
        'price_label': 'Custom',
        'period': 'tailored contract',
        'description': 'For ERP integrations, compliance teams, and high-volume signing.',
        'signing_quota': 'Unlimited / custom terms',
        'gst_quota': 'Unlimited / custom terms',
        'highlights': (
            'USB DSC at scale across PCs',
            'ERP & Business Central integrations',
            'SLA & security review support',
            'Custom allowed origins & IT policies',
        ),
        'cta_label': 'Talk to Incite Gravity',
        'cta_url_name': 'marketing_contact',
        'featured': False,
    },
)

FEATURE_GROUPS = (
    {
        'title': 'Signing',
        'items': (
            ('Class 3 USB DSC', 'PKCS#11 signing via the IG E-Sign Windows agent — private key never leaves the token.'),
            ('PFX API', 'REST API with inline PFX or saved certificate aliases and automatic anchor placement.'),
            ('Portal signing', 'Upload, preview placement with PDF.js, sign in-browser, and download.'),
            ('Free trial sign', 'Try signing without an account — watermarked output for evaluation.'),
        ),
    },
    {
        'title': 'Compliance & audit',
        'items': (
            ('SHA-256 audit trail', 'Hash before/after, document type, client IP, and endpoint on every signature.'),
            ('ISO 27001:2022', 'Built by Incite Gravity, an ISO 27001:2022 certified security partner.'),
            ('Tenant isolation', 'Per-organization API keys, certificates, and usage quotas.'),
            ('Rate limiting', 'Built-in throttling on signing and GST API endpoints.'),
        ),
    },
    {
        'title': 'GST & integrations',
        'items': (
            ('GSTIN lookup', 'Registration details, filing preferences, and return status from one dashboard.'),
            ('E-way bill print', 'Download detailed, regular, or consolidate E-way bill PDFs by e-way bill number.'),
            ('E-invoice print (IRN)', 'Download e-invoice PDFs using the 64-character Invoice Reference Number.'),
            ('REST API', 'Programmatic GSTIN, E-way, and e-invoice calls with a separate monthly GST quota.'),
            ('Developer docs', 'Interactive API reference with code samples in multiple languages.'),
            ('ERP ready', 'Designed for Business Central and custom backends calling localhost USB agents.'),
        ),
    },
)

PRICING_FAQ = (
    (
        'What is included in the IG E-Sign Free plan?',
        'The Free plan includes 100 PDF signatures and 50 GST lookups per month, API keys, '
        'portal signing, USB DSC agent support, GSTIN / E-way bill / e-invoice services, '
        'and audit logging.',
    ),
    (
        'Do I need a USB token for every feature?',
        'No. PFX API and portal signing work with uploaded certificates. USB Class 3 DSC is optional '
        'for workflows that require the private key to remain on a hardware token.',
    ),
    (
        'How do Pro and Enterprise plans work?',
        'Paid plans use quota entitlements managed by Incite Gravity. Contact us for custom signing '
        'volume, GST lookup limits, team features, and annual terms.',
    ),
)

def _breadcrumbs(*segments: tuple[str, str]) -> list[tuple[str, str]]:
    base = site_base_url()
    crumbs = [('Home', f'{base}/')]
    crumbs.extend(segments)
    return crumbs


def get_structured_data_for_view(request) -> list[str]:
    view_name = ''
    if getattr(request, 'resolver_match', None) and request.resolver_match:
        view_name = request.resolver_match.url_name or ''

    meta = PUBLIC_PAGE_META.get(view_name, {})
    description = meta.get('description', '')
    title = meta.get('title', 'IG E-Sign')

    if view_name == 'home':
        return build_structured_data(
            request,
            page_name=title,
            page_description=description,
            breadcrumbs=_breadcrumbs(),
            include_product=True,
        )
    if view_name == 'marketing_features':
        url = f'{site_base_url()}/features/'
        return build_structured_data(
            request,
            page_name=title,
            page_description=description,
            breadcrumbs=_breadcrumbs(('Features', url)),
            include_product=True,
        )
    if view_name == 'marketing_pricing':
        url = f'{site_base_url()}/pricing/'
        return build_structured_data(
            request,
            page_name=title,
            page_description=description,
            breadcrumbs=_breadcrumbs(('Pricing', url)),
            faq_items=PRICING_FAQ,
            include_product=True,
        )
    if view_name == 'marketing_privacy':
        url = f'{site_base_url()}/legal/privacy/'
        return build_structured_data(
            request,
            page_name=title,
            page_description=description,
            breadcrumbs=_breadcrumbs(('Privacy', url)),
        )
    if view_name == 'marketing_terms':
        url = f'{site_base_url()}/legal/terms/'
        return build_structured_data(
            request,
            page_name=title,
            page_description=description,
            breadcrumbs=_breadcrumbs(('Terms', url)),
        )
    if view_name == 'blog_index':
        url = f'{site_base_url()}/blog/'
        return build_structured_data(
            request,
            page_name=title,
            page_description=description,
            breadcrumbs=_breadcrumbs(('Blog', url)),
        )
    if view_name == 'blog_post':
        slug = ''
        if getattr(request, 'resolver_match', None) and request.resolver_match:
            slug = request.resolver_match.kwargs.get('slug', '')
        post = get_post(slug)
        if not post:
            return []
        url = f'{site_base_url()}{post.url_path}'
        return build_structured_data(
            request,
            page_name=post.seo_title,
            page_description=post.description,
            breadcrumbs=_breadcrumbs(('Blog', f'{site_base_url()}/blog/'), (post.title, url)),
            article={
                'headline': post.title,
                'description': post.description,
                'url': url,
                'date_published': post.published.isoformat(),
                'date_modified': post.updated.isoformat(),
                'image': og_image_url(),
            },
        )
    return []


MARKETING_TEMPLATE_CONTEXT = {'marketing_public_layout': True}


@require_http_methods(['GET'])
def features_view(request):
    return render(
        request,
        'accounts/marketing/features.html',
        {**MARKETING_TEMPLATE_CONTEXT, 'feature_groups': FEATURE_GROUPS},
    )


@require_http_methods(['GET'])
def pricing_view(request):
    return render(
        request,
        'accounts/marketing/pricing.html',
        {
            **MARKETING_TEMPLATE_CONTEXT,
            'pricing_tiers': PRICING_TIERS,
            'pricing_faq': PRICING_FAQ,
        },
    )


@require_http_methods(['GET'])
def privacy_view(request):
    return render(request, 'accounts/marketing/privacy.html', MARKETING_TEMPLATE_CONTEXT)


@require_http_methods(['GET'])
def terms_view(request):
    return render(request, 'accounts/marketing/terms.html', MARKETING_TEMPLATE_CONTEXT)


@require_http_methods(['GET'])
def marketing_contact_view(request):
    return redirect('https://incitegravity.com/contact')


@require_http_methods(['GET'])
def blog_index_view(request):
    return render(
        request,
        'accounts/marketing/blog_index.html',
        {**MARKETING_TEMPLATE_CONTEXT, 'posts': all_posts()},
    )


@require_http_methods(['GET'])
def blog_post_view(request, slug: str):
    post = get_post(slug)
    if not post:
        raise Http404('Post not found')
    return render(
        request,
        'accounts/marketing/blog_post.html',
        {**MARKETING_TEMPLATE_CONTEXT, 'post': post},
    )
