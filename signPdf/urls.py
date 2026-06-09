from django.urls import path

from .views import PDFPfxSignAPIView

urlpatterns = [
    path('signpdf-pfx', PDFPfxSignAPIView.as_view()),
]
