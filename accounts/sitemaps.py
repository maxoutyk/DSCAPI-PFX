from datetime import datetime, time, timezone as dt_timezone
from urllib.parse import urlparse

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from .blog import all_posts
from .seo import PUBLIC_SITEMAP_PAGES, site_base_url


def _sitemap_site():
    parsed = urlparse(site_base_url())
    return type('_SitemapSite', (), {'domain': parsed.netloc})(), parsed.scheme or 'https'


class PublicMarketingSitemap(Sitemap):
    """Auto-generated sitemap for public IG E-Sign marketing routes."""

    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return PUBLIC_SITEMAP_PAGES

    def location(self, item):
        return reverse(item.url_name)

    def changefreq(self, item):
        return item.changefreq

    def priority(self, item):
        return item.priority

    def lastmod(self, item):
        return timezone.now()

    def get_urls(self, page=1, site=None, protocol=None):
        site, protocol = _sitemap_site()
        return super().get_urls(page=page, site=site, protocol=protocol)


class BlogPostSitemap(Sitemap):
    """Individual blog articles for the content hub."""

    changefreq = 'monthly'
    priority = 0.7

    def items(self):
        return all_posts()

    def location(self, item):
        return item.url_path

    def lastmod(self, item):
        return datetime.combine(item.updated, time.min, tzinfo=dt_timezone.utc)

    def get_urls(self, page=1, site=None, protocol=None):
        site, protocol = _sitemap_site()
        return super().get_urls(page=page, site=site, protocol=protocol)
