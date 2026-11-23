from django.urls import path
from . import views

app_name = "home"

urlpatterns = [
    path('', views.home_view, name='home'),
    path('scan/', views.scan_page, name='scan'),
    path('scan/analyze/', views.analyze_view, name='analyze'),
    path('scan/analyze-text/', views.analyze_text_view, name='analyze_text'),
    path('history/', views.history_view, name='history'),
    path('history/<int:scan_id>/', views.history_detail_view, name='history_detail'),
    path('history/<int:scan_id>/delete/', views.history_delete_view, name='history_delete'),
    path('staff/scan-activity/', views.scan_activity_view, name='scan_activity'),
]
