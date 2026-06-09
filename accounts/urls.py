from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('verify-email/<uuid:token>/', views.verify_email_view, name='verify_email'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/keys/', views.keys_view, name='keys'),
    path('dashboard/certs/', views.certs_view, name='certs'),
    path('dashboard/docs/', views.docs_view, name='docs'),
]
