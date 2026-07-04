"""
URL configuration for DSCApi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include

from accounts.seo_views import robots_txt_view
from accounts.sitemaps import BlogPostSitemap, PublicMarketingSitemap

sitemaps = {
    'marketing': PublicMarketingSitemap,
    'blog': BlogPostSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', robots_txt_view, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django_sitemap'),
    path('', include('accounts.urls')),
    path('', include('usb_agent.portal_urls')),
    path('', include('gst.portal_urls')),
    path('api/', include('signPdf.urls')),
    path('api/', include('usb_agent.urls')),
    path('api/', include('gst.urls')),
    path('api/', include('accounts.api_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
