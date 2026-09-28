"""
URL configuration for the Likha project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.login.urls')),
    path('', include('apps.register.urls')),
    path('', include('apps.home.urls')),
    path('', include('apps.profile.urls')),
    path('', include('apps.user_settings.urls')),
]
