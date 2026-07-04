"""JSON-LD structured data builders for IG E-Sign marketing pages."""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest

from .seo import BRAND_NAME, PRODUCT_NAME, TAGLINE, site_base_url


def _json_ld(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def organization_schema() -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        'name': BRAND_NAME,
        'url': 'https://incitegravity.com/',
        'logo': f'{site_base_url()}/static/accounts/img/ig-logo-light.png',
        'slogan': TAGLINE,
        'sameAs': [
            'https://incitegravity.com/',
        ],
    }


def website_schema() -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': PRODUCT_NAME,
        'alternateName': f'{PRODUCT_NAME} by {BRAND_NAME}',
        'url': site_base_url(),
        'description': (
            'Digital PDF signing with Class 3 DSC USB tokens, PFX API, GSTIN lookups, '
            'E-way bill and e-invoice PDF print, and browser-based signatures for Indian businesses.'
        ),
        'publisher': {
            '@type': 'Organization',
            'name': BRAND_NAME,
        },
    }


def software_application_schema() -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        'name': PRODUCT_NAME,
        'applicationCategory': 'BusinessApplication',
        'operatingSystem': 'Web, Windows',
        'url': site_base_url(),
        'description': (
            'SaaS platform for Class 3 DSC USB signing, PFX API integration, '
            'portal PDF signing, GSTIN verification, E-way bill print, and e-invoice (IRN) print.'
        ),
        'offers': {
            '@type': 'Offer',
            'price': '0',
            'priceCurrency': 'INR',
            'description': 'Free tier with monthly signing quota',
        },
        'provider': {
            '@type': 'Organization',
            'name': BRAND_NAME,
        },
    }


def breadcrumb_schema(*, items: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {
                '@type': 'ListItem',
                'position': index,
                'name': label,
                'item': url,
            }
            for index, (label, url) in enumerate(items, start=1)
        ],
    }


def web_page_schema(*, name: str, description: str, url: str) -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'WebPage',
        'name': name,
        'description': description,
        'url': url,
        'isPartOf': {
            '@type': 'WebSite',
            'name': PRODUCT_NAME,
            'url': site_base_url(),
        },
    }


def faq_page_schema(*, items: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': question,
                'acceptedAnswer': {
                    '@type': 'Answer',
                    'text': answer,
                },
            }
            for question, answer in items
        ],
    }


def article_schema(
    *,
    headline: str,
    description: str,
    url: str,
    date_published: str,
    date_modified: str,
    image: str,
) -> dict[str, Any]:
    return {
        '@context': 'https://schema.org',
        '@type': 'Article',
        'headline': headline,
        'description': description,
        'url': url,
        'mainEntityOfPage': url,
        'datePublished': date_published,
        'dateModified': date_modified,
        'image': [image],
        'author': {
            '@type': 'Organization',
            'name': BRAND_NAME,
            'url': 'https://incitegravity.com/',
        },
        'publisher': {
            '@type': 'Organization',
            'name': BRAND_NAME,
            'logo': {
                '@type': 'ImageObject',
                'url': f'{site_base_url()}/static/accounts/img/ig-logo-light.png',
            },
        },
    }


def build_structured_data(
    request: HttpRequest,
    *,
    page_name: str,
    page_description: str,
    breadcrumbs: list[tuple[str, str]] | None = None,
    faq_items: list[tuple[str, str]] | None = None,
    include_product: bool = False,
    article: dict[str, str] | None = None,
) -> list[str]:
    """Return JSON-LD script bodies for the current page."""
    canonical = breadcrumbs[-1][1] if breadcrumbs else site_base_url()
    scripts: list[str] = [
        _json_ld(organization_schema()),
        _json_ld(website_schema()),
        _json_ld(web_page_schema(name=page_name, description=page_description, url=canonical)),
    ]
    if include_product:
        scripts.append(_json_ld(software_application_schema()))
    if breadcrumbs and len(breadcrumbs) > 1:
        scripts.append(_json_ld(breadcrumb_schema(items=breadcrumbs)))
    if faq_items:
        scripts.append(_json_ld(faq_page_schema(items=faq_items)))
    if article:
        scripts.append(
            _json_ld(
                article_schema(
                    headline=article['headline'],
                    description=article['description'],
                    url=article['url'],
                    date_published=article['date_published'],
                    date_modified=article['date_modified'],
                    image=article['image'],
                ),
            ),
        )
    return scripts
