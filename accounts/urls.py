from django.urls import path

from . import public_sign_views, views

urlpatterns = [
    path('', views.home, name='home'),
    path('sign/free/', public_sign_views.public_sign_view, name='public_sign'),
    path('sign/free/preview/', public_sign_views.public_sign_preview_view, name='public_sign_preview'),
    path('sign/free/done/', public_sign_views.public_sign_done_view, name='public_sign_done'),
    path('sign/free/download/', public_sign_views.public_sign_download_view, name='public_sign_download'),
    path('register/', views.register_view, name='register'),
    path('verify-email/<uuid:token>/', views.verify_email_view, name='verify_email'),
    path('resend-verification/', views.resend_verification_view, name='resend_verification'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_request_view, name='password_reset'),
    path('reset-password/<uuid:token>/', views.password_reset_confirm_view, name='password_reset_confirm'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/keys/', views.keys_view, name='keys'),
    path('dashboard/certs/', views.certs_view, name='certs'),
    path('dashboard/docs/', views.docs_view, name='docs'),
    path('dashboard/docs/download/', views.docs_download_view, name='docs_download'),
    path('dashboard/signature/', views.signature_style_view, name='signature_style'),
    path('dashboard/signature/new/', views.signature_style_edit_view, name='signature_style_create'),
    path('dashboard/signature/<int:style_id>/', views.signature_style_edit_view, name='signature_style_edit'),
    path('dashboard/signature/<int:style_id>/delete/', views.signature_style_delete_view, name='signature_style_delete'),
    path('dashboard/signature/<int:style_id>/default/', views.signature_style_default_view, name='signature_style_default'),
    path('dashboard/sign/', views.sign_view, name='sign'),
    path('dashboard/sign/preview/', views.sign_preview_view, name='sign_preview'),
    path('dashboard/sign/done/', views.sign_done_view, name='sign_done'),
    path('dashboard/sign/download/', views.sign_download_view, name='sign_download'),
]
