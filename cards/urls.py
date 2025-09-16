from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('create/', views.create_card, name='create_card'),
    path('card/<slug:slug>/', views.view_card, name='view_card'),
    path('card/<slug:slug>/edit/', views.edit_card, name='edit_card'),
    path('my-admin/login/', views.admin_login_view, name='admin_login'),
    path('my-admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('my-admin/card/<slug:slug>/delete/', views.delete_card_admin, name='delete_card_admin'),
    path('documentation/', views.documentation_view, name='documentation'),
    path('password_reset/request_otp/', views.password_reset_request_otp, name='password_reset_request_otp'),
    path('password_reset/verify_otp/', views.password_reset_verify_otp, name='password_reset_verify_otp'),
]